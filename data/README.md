# Authoritative data layout

The pipeline resolves all authoritative inputs from this directory. Keep the
following structure and filenames unchanged:

```text
data/
├── KG/
│   ├── DB100K/
│   │   ├── DB100K.nt
│   │   └── DB100K.tsv
│   ├── YAGO3-10/
│   │   ├── YAGO3-10.nt
│   │   └── YAGO3-10.tsv
│   └── FrenchRoyalty/
│       └── french_royalty.nt
├── Constraints/
│   ├── DB100K/
│   │   ├── db100k.ttl
│   │   ├── db100k.ttl.backup_before_fix_shacl
│   │   └── result_DB100K/
│   │       ├── stats.txt
│   │       ├── targets_valid.log
│   │       ├── targets_violated.log
│   │       ├── validation.log
│   │       └── validationReport.ttl
│   ├── FrenchRoyalty/
│   │   ├── FrenchRoyalty.ttl
│   │   ├── FrenchRoyalty.ttl.backup_before_fix_shacl
│   │   └── result_FrenchRoyalty/
│   │       ├── stats.txt
│   │       ├── targets_valid.log
│   │       ├── targets_violated.log
│   │       ├── traces.csv
│   │       ├── validation.log
│   │       └── validationReport.ttl
│   └── YAGO3-10/
│       ├── YAGO3-10.ttl
│       ├── YAGO3-10.ttl.backup_before_fix_shacl
│       └── result_YAGO3-10/
│           ├── stats.txt
│           ├── targets_valid.log
│           ├── targets_violated.log
│           ├── validation.log
│           └── validationReport.ttl
└── Rules/
    ├── DB100K.csv
    ├── YAGO3-10.csv
    └── french_royalty.csv
```

## Authoritative inputs

- `KG/*` contains the knowledge graphs used by the benchmark.
- `Rules/*.csv` contains the authoritative CoPCA rule exports.
- `Constraints/*/*.ttl` contains the authoritative CoPCA SHACL shapes.
- `Constraints/*/result_*` contains validation outputs and audit references;
  these logs are not used as the SHACL shapes source.
- `*.backup_before_fix_shacl` files are retained only as provenance/audit
  snapshots when supplied with the experiment package.

The runtime does **not** require the TSV companions for RDF loading; DB100K
and YAGO3-10 use their canonical N-Triples files, while FrenchRoyalty uses
its canonical Turtle file.

## Data availability

The repository code expects the authoritative data above but does not invent
or substitute missing source files. The large **DB100K** and **YAGO3-10**
knowledge graphs are distributed through the project's Figshare archive:

**Figshare dataset archive:**
https://figshare.com/s/ebb3a0b4a2fe8e8adf31

Download the required source files from that archive and place them under the
canonical `data/KG/DB100K/` and `data/KG/YAGO3-10/` directories shown above.
Do not rename the files expected by the loader. The repository does not vendor
these large source graphs in Git. If other authoritative source files are kept
outside Git, keep the same directory layout locally and use the
`DATA_ROOT_OVERRIDE` mechanism below.

For a non-default location, set:

```bash
export DATA_ROOT_OVERRIDE=/path/to/data
```

The override must contain `KG/`, `Constraints/`, and `Rules/` exactly as shown
above. Runtime checkpoints and generated artifacts remain under the configured
project runtime root.
