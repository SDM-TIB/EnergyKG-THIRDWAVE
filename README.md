# ThirdWave Knowledge Graph — Renewable Energy Assessment (Sub-Saharan Africa)

Neuro-symbolic knowledge graph for renewable energy resource assessment (wind, solar, hydro),
extracted from ~340 research papers and grounded in a domain ontology.

## Contents
- `thirdwave_kg.nt` — the knowledge graph (N-Triples, ~106,500 triples, ~15,600 entities)
- `energy_ontology.ttl` — the domain ontology (v15)

## Key features
- Canonical concepts reused across papers (one Weibull with its formula, reused everywhere)
- Wikidata alignment via `owl:sameAs` (~100 concepts)
- Objectives typed by their sub-class; ORKG-style structuring
- ~94% of entities in a single connected component (network analysis)

## Namespaces
- ontology: `https://w3id.org/thirdwave/ontology#`
- data (paper-specific instances): `https://w3id.org/thirdwave/data/`
- resource (shared canonical concepts): `https://w3id.org/thirdwave/resource/`

## Load (Apache Jena)
```bash
riot --validate thirdwave_kg.nt
# load ontology + graph together for the class hierarchy:
arq --data energy_ontology.ttl --data thirdwave_kg.nt --query your_query.sparql
```

## Status
Work in progress. Entity-by-entity renormalization ongoing; ontology alignment to
OEO / STATO / OntoDM / ENVO in progress for interoperability.

## License
CC-BY-4.0
