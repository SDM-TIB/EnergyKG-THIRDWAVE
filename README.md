[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# Constraint-Gated Neuro-Symbolic KG-RAG: Evidence Admission Under Deliberate Knowledge Incompleteness

Welcome to the official repository for this project, which harmonizes three
prior lines of work — **BRINK**'s incomplete-knowledge benchmark protocol,
**CoPCA**'s constraint-aware symbolic learning, and **DIGIMON**'s
retriever taxonomy — into a single, reproducible pipeline that tests whether a
SHACL constraint gate makes symbolic evidence more trustworthy for a language
model, or whether an observed effect comes mostly from *how* that evidence is
labeled when it is shown to the model.

---

## Overview

The **pipeline** follows these major steps:

1. **Loading** of the authoritative knowledge graph (raw RDF, CoPCA rules, CoPCA SHACL shapes).
2. **Freezing** of a BRINK-style benchmark split (8:1:1 base policy, SHA-256 fingerprinted, with a documented 100-item test floor for small pools).
3. **Mining** of Horn rules over the KG using AMIE3, at the CoPCA/BRINK confidence threshold.
4. **Neuro-symbolic inference**: forward-chain once on the complete graph, then backward-chain (prove) each candidate against only the incomplete graph.
5. **Constraint validation**: a differential SHACL gate ($\Delta$SHACL) admits a candidate only if it introduces no new validation-result signature.
6. **Evidence fusion and generation**: build a fixed-size context under eight controlled conditions (E0–E7), and generate an answer with a local LLM.
7. **Evaluation**: score with BRINK's metrics (Hits@Any, Hits@Hard, HHR, F1).

> Example question: *"Who is the successor of Ferdinand IV of Castile?"* — the
> direct supporting fact is removed on purpose; the pipeline must decide
> whether a rule-based guess is trustworthy enough to answer correctly.

---

## 📁 Repository Structure

```
├── src/
│   ├── setup/                  # platform detection, global configuration, source preflight
│   ├── utils/                  # canonicalization, hashing, serialization
│   ├── KG/                     # authoritative dataset loader
│   ├── Rules/                  # AMIE-mined Horn rule parsing + statistics
│   ├── Constraints/            # SHACL loading + the ΔSHACL validation gate
│   ├── Symbolic_Learning/      # grounding engine, benchmark construction, question generation,
│   │                           #   retrieval indexes, backward-chaining neuro-symbolic inference
│   ├── Evidence_Fusion/        # the eight evidence conditions (E0-E7)
│   ├── Generation/             # local LLM runtime (Qwen2.5-3B, Llama-3.1-8B) + answer generation
│   ├── Evaluation/             # driver, audits, metrics, figures, final manifest
│   └── main.py                 # command-line entry point
│
├── tests/
│   ├── test_pure_functions.py  # unit tests for canonicalization, metrics, rule/answer parsing
│   └── README.md               # how to test the pipeline, including the end-to-end smoke test
│
├── data/
│   ├── KG/                     # DB100K, YAGO3-10 and FrenchRoyalty graphs
│   ├── Constraints/            # authoritative CoPCA SHACL shapes + audit outputs
│   ├── Rules/                  # authoritative CoPCA rule exports
│   └── README.md               # canonical data layout and acquisition notes
│
├── results/
│   ├── FrenchRoyalty/          # frozen fingerprints + per-condition metrics
│   ├── DB100K/
│   └── YAGO3-10/
│
├── docs/
│   ├── METHODOLOGY.md          # full algorithmic detail, every deliberate BRINK/CoPCA deviation
│   └── KNOWN_LIMITATIONS.md    # documented, not hidden
│
├── scripts/
│   └── launch.sh               # unattended, resumable launch for a persistent VM
│
├── requirements.txt
├── .gitignore
└── LICENSE
```


The files under `src/` share global state across stages (like a notebook's
cells), so they run in a fixed order through `src/main.py`, not as
independently importable modules.

---

## Benchmark Statistics

| **KG Size** | **Benchmark**  | **#Triples** | **#Entities** | **#Relations** | **Frozen test questions** |
| ----------- | -------------- | -----------: | ------------: | --------------: | -------------------------: |
| **Small**   | FrenchRoyalty  | 12,265       | 2,644         | 11              | 100                        |
| **Large**   | DB100K         | 787,933      | 99,244        | 469             | 231                        |
| **Medium**  | YAGO3-10       | ~1,080,264   | 123,150       | 37              | 100                        |

Each split is fingerprinted (pool SHA-256, split SHA-256); see
`results/<KG>/fingerprints.txt` to verify that a re-run reproduces the exact
same benchmark before comparing new numbers to those already reported.

### The eight evidence conditions

| Condition | Incomplete KG? | Symbolic evidence | Purpose |
|---|:---:|---|---|
| E0 | No | — | Ceiling: complete graph |
| E1 | Yes | None | Baseline |
| E2 | Yes | PCA-filtered candidates | Does symbolic inference help? |
| E3 | Yes | Unfiltered candidates | Does the PCA threshold matter? |
| E4 | Yes | Random distractors | Volume vs. relevance control |
| E5 | No | PCA-filtered candidates | Ceiling for the symbolic mechanism |
| E6 | Yes | Oracle (true removed fact) | Upper bound |
| E7 | Yes | $\Delta$SHACL-filtered candidates | Does constraint gating help? |

---

## Evaluation Metrics

Following BRINK's metric definitions exactly:

- **Hits@Any** — is at least one predicted answer correct?
- **Hits@Hard** — is the specific "hard" answer (the one whose direct
  supporting fact was removed) among the predictions?
- **HHR (Hard Hits Rate)** — `Hits@Hard / Hits@Any`
- **Precision / Recall / F1** — per-question, over the predicted vs. gold answer sets

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/admhamza/constraint-gated-neurosymbolic-kg-rag.git
cd constraint-gated-neurosymbolic-kg-rag
```

### 2. Create a Virtual Environment and Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Obtain the Authoritative Data Sources

The pipeline resolves authoritative inputs from the canonical `data/` tree. See
[`data/README.md`](data/README.md) for the exact filenames and layout. If the
source package is kept outside Git for licensing or size reasons, mirror the
same tree locally and set `DATA_ROOT_OVERRIDE`.

### On Kaggle: match the VM's Python version

Kaggle's default kernel runs Python 3.12, under which `pyshacl` fails to
evaluate FrenchRoyalty's SPARQL-based shape (every candidate resolves as
`unresolved`, silently collapsing E7 to E1 -- see
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md), item 3). Run this
once per Kaggle session, before anything else:

```bash
!bash scripts/setup_kaggle_py310.sh
```

This installs Python 3.10 (confirmed working) in a dedicated venv. From then
on, `src/setup/platform_detection.py` auto-detects a non-3.10 interpreter and
transparently re-executes itself under that venv, so ordinary invocations
(`!python3 src/main.py ...`) already use 3.10 without any further change. If
the venv is not found, a prominent warning is printed instead of silently
proceeding on a broken version.

### Step-by-Step Instructions

#### Step 1: Choose one, several, or all KGs / retrievers / backbones

By default, no question count is capped and no staged tiering is enabled. The frozen split is the project’s BRINK-style adaptation (including the documented small-pool test floor), not the released BRINK dataset split.

```bash
# One KG, default retriever (onehop), both local backbones, full frozen split
python3 src/main.py --dataset FrenchRoyalty

# Several KGs and several retrievers at once
python3 src/main.py --dataset FrenchRoyalty DB100K --retriever onehop tog

# Every KG, every retriever
python3 src/main.py --dataset all --retriever all

# One backbone only
python3 src/main.py --dataset FrenchRoyalty --model Qwen2.5-3B

# Staged checkpoints (BRINK-style tiers) instead of a single full pass
python3 src/main.py --dataset FrenchRoyalty --tiers 10 50 100

# A hard cap on question count, overriding BRINK's frozen split size
python3 src/main.py --dataset FrenchRoyalty --max-questions 5
```

Local backbones (default, no API key needed) vs. a remote, OpenAI-compatible
API instead of local weights (any provider that speaks the OpenAI
chat-completions format: OpenAI, Groq, Together, a local vLLM/Ollama server,
etc.):

```bash
export LLM_API_KEY="sk-..."   # preferred over --api-key, keeps it out of shell history
python3 src/main.py --dataset FrenchRoyalty --backend api \
    --api-provider groq --api-model-name llama-3.1-8b-instant
```

`--api-provider` is a shortcut for `--api-base-url`, covering `openai`,
`groq`, `together`, `fireworks`, `deepinfra`. For any other OpenAI-compatible
endpoint (a different provider, or a local vLLM/Ollama server), pass
`--api-base-url` directly instead:

```bash
python3 src/main.py --dataset FrenchRoyalty --backend api \
    --api-base-url http://localhost:8000/v1 --api-model-name my-local-model
```

The key is read once, at launch, and never printed or written to any log or
checkpoint file.

Run `python3 src/main.py --help` for the full list of options (`--dataset`,
`--retriever`, `--model`, `--tiers`, `--backend`, `--api-key`,
`--api-model-name`, `--api-provider`, `--api-base-url`, `--max-questions`,
`--campaign-name`, `--root`, `--stop-after-split`).

#### 🔍 Step 2: Scale up once a small run succeeds

```bash
python3 src/main.py --dataset FrenchRoyalty --max-questions 5   # smoke test first
python3 src/main.py --dataset FrenchRoyalty                     # then the full frozen split
python3 src/main.py --dataset DB100K --retriever onehop tog
```

For an unattended, resumable run on a persistent VM (survives an SSH
disconnect), use `scripts/launch.sh` instead of calling `main.py` directly.

#### 🔍 Step 3: Verify reproducibility

Compare the printed `pool_sha256` / `split_sha256` for your run against
`results/<KG>/fingerprints.txt` before treating any new number as comparable
to those already reported.

---

## Testing

See [`tests/README.md`](tests/README.md) for the full testing strategy. In
short:

```bash
python3 -m pytest tests/                                       # unit tests, no data or GPU needed
python3 src/main.py --dataset FrenchRoyalty --stop-after-split # split-construction smoke test, no GPU
python3 src/main.py --dataset FrenchRoyalty --max-questions 2  # end-to-end smoke test, needs a GPU/CPU + data
```

---

## Benchmarks Included

- **FrenchRoyalty** — small, clean royal-family knowledge graph
- **DB100K** — large, general-domain knowledge graph
- **YAGO3-10** — medium, Wikipedia-derived general knowledge graph

Authoritative source files for all three are distributed by the CoPCA
project (see [`data/README.md`](data/README.md)); this repository computes
and freezes its own benchmark split, question set, and symbolic-inference
artifacts from those sources.

---

## Referenced Works

This project builds directly on, and clearly documents every deviation from,
the following:

- **BRINK** — Zhou, D. et al. *What Breaks Knowledge Graph based RAG?
  Benchmarking and Empirical Insights into Reasoning under Incomplete
  Knowledge.* EACL 2026.
  DOI: [10.18653/v1/2026.eacl-long.114](https://aclanthology.org/2026.eacl-long.114) ·
  [github.com/boschresearch/brink](https://github.com/boschresearch/brink)
- **CoPCA** — Purohit, D., Chudasama, Y., Vidal, M.-E. *Capturing Symbolic
  Knowledge of Constraints and Incompleteness to Guide Inductive Learning in
  Neuro-Symbolic Knowledge Graph Completion.* K-CAP 2025.
  DOI: [10.1145/3731443.3771355](https://doi.org/10.1145/3731443.3771355) ·
  [github.com/SDM-TIB/CoPCA](https://github.com/SDM-TIB/CoPCA)
- **DIGIMON** — Zhou, Y. et al. *In-depth Analysis of Graph-based RAG in a
  Unified Framework.* arXiv:2503.04338 ·
  [github.com/JayLZhou/GraphRAG](https://github.com/JayLZhou/GraphRAG)
- **VANILLA** — Purohit, D., Chudasama, Y., Vidal, M.-E. *VANILLA: Validated
  Knowledge Graph Completion — A Normalization-based Framework for
  Integrity, Link Prediction, and Logical Accuracy.* Knowledge-Based
  Systems, 2025. DOI: [10.1016/j.knosys.2025.113939](https://doi.org/10.1016/j.knosys.2025.113939)
- **AMIE 3** — Lajus, J., Galárraga, L., Suchanek, F. *Fast and Exact Rule
  Mining with AMIE 3.* ESWC 2020. DOI: [10.1007/978-3-030-49461-2_3](https://doi.org/10.1007/978-3-030-49461-2_3)
- **SHACL** — W3C. *Shapes Constraint Language.* W3C Recommendation, 2017.
  [w3.org/TR/shacl](https://www.w3.org/TR/shacl/)
- **YAGO3** — Mahdisoltani, F., Biega, J., Suchanek, F. *YAGO3: A Knowledge
  Base from Multilingual Wikipedias.* CIDR 2015.
- **DB100K** — Ding, B., Wang, Q., Wang, B., Guo, L. *Improving Knowledge
  Graph Embedding Using Simple Constraints.* ACL 2018. arXiv:1805.02408

Every deliberate departure from BRINK's or CoPCA's own published protocol is
listed explicitly in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — nothing
here is presented as exact conformance where it is not.

---

## Authors & Contact

This work is carried out within the **THIRDWAVE** project — *Neuro-symbolic
AI and Large Language Models* (Horizon Europe MSCA, Grant Agreement
101236394) — a collaboration between:

- **TIB – Leibniz Information Centre for Science and Technology / L3S
  Research Center**, Hannover, Germany —
  [thirdwave.l3s.uni-hannover.de](https://thirdwave.l3s.uni-hannover.de/) ·
  [CORDIS project page](https://cordis.europa.eu/project/id/101236394)
- **University of Yaoundé I**, Yaoundé, Cameroon —
  [www.uy1.uninet.cm](https://www.uy1.uninet.cm)

**Developed by:**
- **Adamou Hamza** — <admhamza@gmail.com>
- **Djuidje Germaine épouse Aloyem** — <kdjuidje@yahoo.fr>

**General supervision:**
- **Prof. Vidal Maria-Esther** — <Maria.Vidal@tib.eu>

Feel free to reach out for any issues related to reproducibility or
implementation.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgements

This project builds upon the BRINK benchmark protocol, the CoPCA
constraint-aware symbolic learning framework and its authoritative SHACL
shapes and rule sources, and the DIGIMON retriever implementations. It was
carried out as part of the THIRDWAVE project, funded by the European Union's
Horizon Europe MSCA programme under Grant Agreement 101236394, with the
support of TIB / L3S Hannover and University of Yaoundé I.
