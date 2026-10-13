# THIRDWAVE renewable-energy knowledge graph

Version of 2026-10-13.

A knowledge graph of wind, solar and hydropower research, built from papers described in the Open Research Knowledge Graph (ORKG).

- 344 papers: 175 wind, 118 solar, 51 hydro.
- 131,840 triples and 15,925 entities.
- 0 domain or range violations and 0 dangling links.
- Connectivity 0.9996 (7 variable nodes have no links).

## Contents

```
ontology/thirdwave_ontology.ttl   the ontology (Turtle)
kg/thirdwave_kg.nt                the knowledge graph (N-Triples)
rml/thirdwave_mapping.ttl         RML rules (212 TriplesMaps) that build kg/ from data/
rml/config.ini                    SDM-RDFizer configuration
data/entities/*.csv               one file per entity type (one row = one instance)
data/relations/*.csv              one file per object property (subject id, target id)
data/alignments/*.csv             SKOS links from shared nodes to QUDT, STATO, OEO, ENVO and SWO
```

## Ontology

- 244 classes, 104 object properties and 224 datatype properties.
- Every term has a `skos:definition` and an `rdfs:comment`.
- 254 SKOS alignments to OEO, STATO, ENVO, QUDT, SOSA, PROV-O, IAO, OBI, FaBiO, BIBO, schema.org, ML-Schema, Dublin Core and DCAT.

## Namespaces

- Ontology: `https://w3id.org/thirdwave/ontology#`
- Instances: `https://w3id.org/thirdwave/data/`

## Rebuilding the graph

From this folder:

```bash
pip install rdfizer
python3 -m rdfizer -c rml/config.ini
```

This writes `kg/thirdwave_kg.nt`. The output is identical to the file in this repository.

## License

MIT (see `LICENSE` at the root of the repository).
