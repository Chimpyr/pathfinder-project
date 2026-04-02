# ScenicPathFinder

A web application for discovering optimal walking routes using multi-criteria route optimisation based on scenery, lighting, and urban qualities.

## Features

- **Multi-criteria Routing**: Score routes by greenness, water proximity, noise levels, social vitality, and built heritage
- **Advanced Pathfinding**: Geometric loop solvers and A\* algorithm with budget constraints
- **Street Lighting Integration**: Safety assessment with visibility and lighting context analysis
- **Interactive Web Interface**: Real-time route visualisation with folium maps and user preference controls

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (for street lighting processor)
- Redis (for Celery task queue)
- Docker (optional)

### Installation

**Using Docker (Recommended)**

```bash
docker-compose up --build
```

See [guides/docker_setup.md](docs/guides/docker_setup.md) for detailed setup and troubleshooting.

**Manual Setup**

```bash
pip install -r requirements.txt
python run.py
```

## Documentation

For a complete overview of the documentation structure, see the [Documentation Index](docs/README.md).

Navigate the system using these key documents:

| Area                 | Documentation                                                                 |
| -------------------- | ----------------------------------------------------------------------------- |
| **Getting Started**  | [Docker setup & debugging](docs/guides/docker_setup.md)                       |
| **Architecture**     | [System design & scalability](docs/architecture/README.md)                    |
| **API Reference**    | [Endpoints](docs/api/api_reference.md) · [Blueprints](docs/api/blueprints.md) |
| **Features**         | [User capabilities](docs/features/README.md)                                  |
| **Algorithms**       | [Pathfinding algorithms](docs/algorithms/README.md)                           |
| **Testing**          | [Street lighting test suite](docs/testing/street_lighting_test_suite.md)      |
| **Design Decisions** | [Architecture Decision Records](docs/decisions/README.md)                     |
| **Future Work**      | [Roadmap](docs/roadmap/future_considerations.md)                              |

## Project Structure

```text
app/              # Flask application & business logic
benchmarks/       # Performance testing suite
tests/            # Unit & integration tests
docs/             # System documentation organised by function
scripts/          # Database bootstrap & utilities
```

## Development

Run tests:

```bash
pytest tests/
```

See [guides/debug_features.md](docs/guides/debug_features.md) for debugging workflows and diagnostics.
