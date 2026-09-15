"""LLM runtime: local (Kaggle Model weights via kagglehub, default) or a
remote OpenAI-compatible API (LLM_BACKEND=api)."""

# Runs before dataset loading: question generation needs cached_chat().
# Local: public Kaggle Models via kagglehub. API: any OpenAI-compatible endpoint;
# credentials are read at call time and never logged.
import time, json, os, random, re, gc
import torch
import kagglehub
import requests
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

_LOADED_MODELS = {}
_RESOLVED_MODEL_PATHS = {}  # model_id -> local path resolved by kagglehub (cached per session)
MODEL_TOKEN_LOG = {
    mid: {"input": 0, "output": 0, "calls": 0, "api_calls": 0, "api_failures": 0,
          "cache_hits": 0, "failures": 0, "retries": 0, "quota_blocked": 0, "auth_blocked": 0}
    for mid in MODEL_ORDER
}
LLM_RUNTIME_STATE = {
    "token_available": False, "token_valid": False, "blocked_models": {},
    "auth_blocked_by_model": {}, "quota_blocked_by_model": {}, "auth_error_by_model": {},
    "last_error": None,
}

class LLMCallError(RuntimeError):
    def __init__(self, message, *, retryable=False, auth=False, quota=False, status_code=None):
        super().__init__(message)
        self.retryable = retryable
        self.auth = auth
        self.quota = quota
        self.status_code = status_code

def _block_model(model_id, *, kind, exc=None):
    LLM_RUNTIME_STATE["blocked_models"][model_id] = kind
    if exc is not None:
        LLM_RUNTIME_STATE["auth_error_by_model"][model_id] = {
            "model_id": model_id, "type": type(exc).__name__,
            "message": str(exc)[:1000], "timestamp": time.time(),
        }

def _device_available():
    return torch.cuda.is_available()

def _resolve_model_path(model_id):
    """Resolve a cached Kaggle model path; download only when needed."""
    if model_id in _RESOLVED_MODEL_PATHS:
        return _RESOLVED_MODEL_PATHS[model_id]
    handle = MODEL_CONFIGS[model_id]["kagglehub_handle"]
    expected_path = Path(os.environ.get("KAGGLEHUB_CACHE", "")) / "models" / handle
    if expected_path.exists() and any(expected_path.glob("*.safetensors")):
        print(f"{model_id}: weights already present locally at {expected_path} -- "
              f"kagglehub.model_download() skipped (working around the bug above).")
        _RESOLVED_MODEL_PATHS[model_id] = str(expected_path)
        return str(expected_path)
    path = kagglehub.model_download(handle)
    _RESOLVED_MODEL_PATHS[model_id] = path
    return path

# Resolves each LOCAL model before launch; a failure blocks only that model.
# API-backend models skip this download entirely.
for _mid in MODEL_ORDER:
    _cfg = MODEL_CONFIGS[_mid]
    if _cfg.get("backend") == "api":
        continue
    try:
        print(f"Resolving {_mid} ({_cfg['kagglehub_handle']}) via kagglehub "
              f"(downloading if not already cached)...")
        _resolved = _resolve_model_path(_mid)
        print(f"OK {_mid}: weights available locally ({_resolved}).")
    except Exception as e:
        print(f"\nFAILED {_mid} DISABLED BEFORE LAUNCH: kagglehub.model_download failed "
              f"({type(e).__name__}: {e})")
        print("   -> check Kaggle authentication (package-installation cell) and the "
              f"handle '{_cfg['kagglehub_handle']}' on kaggle.com/models.")
        _block_model(_mid, kind="load_error", exc=e)

def _load_model_local(model_id):
    path = _resolve_model_path(model_id)
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    if _device_available():
        try:
            bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                                      bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
            model = AutoModelForCausalLM.from_pretrained(
                path, quantization_config=bnb, device_map="auto", low_cpu_mem_usage=True)
            kind = "gpu-4bit"
        except Exception as e:
            print(f"[{model_id}] 4-bit loading failed ({e}); falling back to fp16 GPU.")
            model = AutoModelForCausalLM.from_pretrained(
                path, torch_dtype=torch.float16, device_map="auto", low_cpu_mem_usage=True)
            kind = "gpu-fp16"
    else:
        model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32, low_cpu_mem_usage=True)
        kind = "cpu-fp32"
    model.eval()
    return {"backend": "local-kagglehub", "tok": tok, "model": model, "kind": kind}

def _get_model(model_id):
    if model_id in LLM_RUNTIME_STATE["blocked_models"]:
        kind = LLM_RUNTIME_STATE["blocked_models"][model_id]
        raise LLMCallError(f"{model_id} disabled for this run ({kind}); no generation attempted.")
    if model_id not in _LOADED_MODELS:
        try:
            print(f"Loading {model_id} from {MODEL_CONFIGS[model_id]['kagglehub_handle']} ...")
            _LOADED_MODELS[model_id] = _load_model_local(model_id)
            print(f"{model_id} loaded ({_LOADED_MODELS[model_id]['kind']}).")
        except Exception as e:
            _block_model(model_id, kind="load_error", exc=e)
            raise LLMCallError(f"Local loading of {model_id} failed: {e}", retryable=False) from e
    return _LOADED_MODELS[model_id]

def _api_key():
    # Read fresh on every call, never stored in a print/log statement.
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise LLMCallError("LLM_API_KEY is not set for API backend.", auth=True)
    return key

def _call_api_chat(model_id, messages, max_tokens, temperature):
    cfg = MODEL_CONFIGS[model_id]
    url = f"{cfg['api_base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    payload = {"model": cfg["api_model_name"], "messages": messages,
               "max_tokens": int(max_tokens), "temperature": float(temperature)}
    resp = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    if resp.status_code == 401 or resp.status_code == 403:
        raise LLMCallError(f"API auth failed (status {resp.status_code}) -- check LLM_API_KEY.",
                            auth=True, status_code=resp.status_code)
    if resp.status_code == 429:
        raise LLMCallError("API rate-limited (status 429).", quota=True, retryable=True, status_code=429)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

def _cache_path(model_id, purpose, payload):
    return CACHE / model_id / purpose / f"{sha_key(payload)}.json"

def _generate_local(model_id, messages, max_tokens, temperature):
    loaded = _get_model(model_id)
    tok, model = loaded["tok"], loaded["model"]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    in_len = int(inputs["input_ids"].shape[1])
    gen_kwargs = dict(max_new_tokens=int(max_tokens), pad_token_id=tok.pad_token_id)
    if temperature and float(temperature) > 0:
        gen_kwargs.update(do_sample=True, temperature=float(temperature))
        if TOP_P is not None:
            gen_kwargs["top_p"] = float(TOP_P)
    else:
        gen_kwargs["do_sample"] = False
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    text = tok.decode(out[0][in_len:], skip_special_tokens=True).strip()
    out_len = int(out.shape[1] - in_len)
    return text, in_len, out_len, loaded["backend"]

def cached_chat(messages, *, model_id=None, max_tokens=48, temperature=0.0, purpose="chat", track_key=None):
    is_api = MODEL_CONFIGS[model_id].get("backend") == "api"
    provider = "api" if is_api else "local-kagglehub"
    payload = {
        "model_id": model_id, "model": MODEL_CONFIGS[model_id].get("api_model_name") or MODEL_CONFIGS[model_id]["kagglehub_handle"],
        "messages": messages, "max_tokens": int(max_tokens), "temperature": float(temperature),
        "purpose": purpose, "track_key": track_key, "provider": provider,
    }
    path = _cache_path(model_id, purpose, payload)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and isinstance(cached.get("text"), str):
                MODEL_TOKEN_LOG[model_id]["cache_hits"] += 1
                return cached["text"]
        except Exception:
            pass
        try:
            path.unlink()
        except Exception:
            pass

    if model_id in LLM_RUNTIME_STATE["blocked_models"]:
        kind = LLM_RUNTIME_STATE["blocked_models"][model_id]
        raise LLMCallError(f"{model_id}: execution disabled ({kind}).")

    last = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            if is_api:
                text, in_len, out_len = _call_api_chat(model_id, messages, max_tokens, temperature)
                backend_name = "api"
            else:
                text, in_len, out_len, backend_name = _generate_local(model_id, messages, max_tokens, temperature)

            MODEL_TOKEN_LOG[model_id]["input"] += in_len
            MODEL_TOKEN_LOG[model_id]["output"] += out_len
            MODEL_TOKEN_LOG[model_id]["calls"] += 1

            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps({
                "text": text, "input_tokens": in_len, "output_tokens": out_len,
                "model_id": model_id, "model": payload["model"],
                "backend": backend_name, "created_at": time.time(),
            }, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
            return text

        except LLMCallError:
            raise
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache(); gc.collect()
            last = exc
            MODEL_TOKEN_LOG[model_id]["retries"] += 1
            if attempt >= LLM_MAX_RETRIES:
                MODEL_TOKEN_LOG[model_id]["failures"] += 1
                raise LLMCallError(f"{model_id}: persistent GPU OOM after {attempt} attempts.", retryable=True) from exc
            delay = min(LLM_BACKOFF_MAX, LLM_BACKOFF_BASE * (2 ** (attempt - 1)))
            print(f"GPU OOM on {model_id}; clearing memory, retrying {attempt+1}/{LLM_MAX_RETRIES} in {delay:.1f}s")
            time.sleep(delay)
        except Exception as exc:
            last = exc
            MODEL_TOKEN_LOG[model_id]["retries"] += 1
            if attempt >= LLM_MAX_RETRIES:
                MODEL_TOKEN_LOG[model_id]["failures"] += 1
                raise LLMCallError(
                    f"Generation for {model_id} failed after {attempt} attempts: {type(exc).__name__}: {exc}",
                    retryable=True
                ) from exc
            delay = min(LLM_BACKOFF_MAX, LLM_BACKOFF_BASE * (2 ** (attempt - 1))) + random.uniform(0, LLM_RETRY_JITTER)
            print(f"Transient error ({type(exc).__name__}) on {model_id}; attempt {attempt+1}/{LLM_MAX_RETRIES} in {delay:.1f}s")
            time.sleep(delay)

    raise LLMCallError(f"Generation failed: {last}", retryable=True)

print("LLM runtime ready.")
print("GPU detected:", _device_available())
for _mid in MODEL_ORDER:
    _cfg = MODEL_CONFIGS[_mid]
    flag = " [BLOCKED -- load/auth failed]" if _mid in LLM_RUNTIME_STATE["blocked_models"] else " [OK]"
    _label = _cfg.get("kagglehub_handle") or f"api:{_cfg.get('api_model_name')}@{_cfg.get('api_base_url')}"
    print(f" - {_mid}: {_label}{flag}")
print("A loading/auth error disables only the affected model; already-validated "
      "checkpoints stay intact and the next model is attempted normally.")
if any(MODEL_CONFIGS[m].get("backend") == "api" for m in MODEL_ORDER):
    print("LLM runtime ready:", MODEL_ORDER)
