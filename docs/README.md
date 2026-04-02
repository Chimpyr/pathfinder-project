# ScenicPathFinder Documentation

This folder is organised by system area and functionality so you can find the
right document quickly.

## Quick Navigation

- System architecture and scaling: [architecture/README.md](architecture/README.md)
- HTTP endpoints and blueprint layout: [api/api_reference.md](api/api_reference.md), [api/blueprints.md](api/blueprints.md)
- Feature docs by user capability: [features/README.md](features/README.md)
- Pathfinding algorithms and routing internals: [algorithms/README.md](algorithms/README.md)
- Docker/dev workflows and debugging: [guides/docker_setup.md](guides/docker_setup.md), [guides/debug_features.md](guides/debug_features.md)
- Test documentation: [testing/street_lighting_test_suite.md](testing/street_lighting_test_suite.md)
- Architecture decisions (ADRs): [decisions/README.md](decisions/README.md)
- Future work and backlog direction: [roadmap/future_considerations.md](roadmap/future_considerations.md)
- Report/poster diagrams: [diagrams/](diagrams/)

## Folder Structure

- `api/`: Public/internal API contracts and endpoint references.
- `architecture/`: System architecture, caching, Celery/Redis, and performance strategy.
- `features/`: Functional behaviour docs (routing, lighting, UI/accounts, saved data).
  - `features/routing/`: Core route scoring and path-selection features.
  - `features/research/`: Method comparisons and deep dives used by routing decisions.
- `algorithms/`: Pathfinding algorithms and technical references.
- `guides/`: Setup, troubleshooting, and operator workflows.
- `testing/`: Test plans and verification docs.
- `decisions/`: ADRs and implementation-plan records.
- `roadmap/`: Future considerations and medium/long-term priorities.
- `diagrams/`: Report and poster diagram source markdown.
- `local/`: Local report notes and working drafts.

## Notes

- Links were updated to match the reorganised structure.
- If you add a new Markdown file, place it in the closest system/function folder
  instead of docs root.
