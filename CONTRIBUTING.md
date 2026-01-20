# Contributing Guide

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Make (optional, but recommended)
- Git

### Quick Start

Using Make:
```bash
make full-setup
```

Manual:
```bash
# 1. Setup environment
cp .env.example .env  # or use: make setup

# 2. Build and start services
docker-compose up --build -d

# 3. Run migrations
docker-compose run --rm api alembic upgrade head

# 4. Seed database
docker-compose run --rm api python -m app.db.seed
```

## Development Workflow

### Making Changes

1. Create a feature branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes

3. Run linter and formatter:
```bash
make lint
make format
```

4. Run tests:
```bash
make test
```

5. Commit your changes:
```bash
git add .
git commit -m "Description of changes"
```

6. Push and create PR:
```bash
git push origin feature/your-feature-name
```

### Running Tests

```bash
# All tests
make test

# API tests only
make test-api

# With coverage
docker-compose run --rm api pytest --cov=app --cov-report=html
```

### Code Style

This project uses:
- **ruff** for linting
- **black** for formatting
- Line length: 120 characters

```bash
# Check linting
make lint

# Auto-format code
make format
```

### Database Migrations

#### Creating a new migration

```bash
# Auto-generate migration
make migrate-create MSG="description of changes"

# Or manually
docker-compose run --rm api alembic revision -m "description"
```

#### Applying migrations

```bash
# Upgrade to latest
make migrate

# Downgrade one version
make migrate-down

# Check current version
docker-compose run --rm api alembic current
```

### Working with Models

When adding or modifying SQLAlchemy models:

1. Create/modify model in `api/app/models/`
2. Import in `api/app/models/__init__.py`
3. Create migration: `make migrate-create MSG="add new model"`
4. Review generated migration in `migrations/versions/`
5. Apply migration: `make migrate`
6. Verify: `make shell-db` and check tables with `\dt`

### Adding New Endpoints

1. Create endpoint file in `api/app/api/v1/endpoints/`
2. Add router to `api/app/api/v1/__init__.py`
3. Create schema in `api/app/schemas/` (if needed)
4. Write tests in `api/tests/`
5. Update API documentation

Example:
```python
# api/app/api/v1/endpoints/items.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.item import Item

router = APIRouter()

@router.get("/")
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).all()
```

### Adding Celery Tasks

1. Create task in `worker/app/tasks/`
2. Register task in `worker/app/celery_app.py`
3. Write tests

Example:
```python
# worker/app/tasks/processing.py
from app.celery_app import celery_app

@celery_app.task(name="app.tasks.process_job")
def process_job(job_id: int) -> dict:
    # Task logic here
    return {"status": "completed"}
```

## Useful Commands

### Docker

```bash
# View logs
make logs              # All services
make logs-api          # API only
make logs-worker       # Worker only
make logs-db           # Database only

# Shell access
make shell-api         # Python shell in API
make shell-worker      # Python shell in Worker
make shell-db          # psql shell in Database

# Restart services
make restart           # All services
docker-compose restart api    # API only
docker-compose restart worker # Worker only
```

### Database

```bash
# Connect to database
make shell-db

# Inside psql:
\dt                    # List tables
\d+ table_name         # Describe table
\di                    # List indexes
SELECT * FROM tenants; # Query data
```

### Debugging

```bash
# View service status
docker-compose ps

# Inspect service
docker-compose logs api
docker-compose exec api env  # View environment variables

# Restart with fresh database
make clean
make full-setup
```

## Testing

### Unit Tests

Create tests in `api/tests/` or `worker/tests/`:

```python
# api/tests/test_tenants.py
def test_list_tenants(client, db):
    response = client.get("/v1/tenants")
    assert response.status_code == 200
```

### Integration Tests

Use fixtures for database and client:

```python
# api/tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)
```

## Code Review Checklist

Before submitting a PR, ensure:

- [ ] Code follows project style (ruff + black)
- [ ] Tests added/updated
- [ ] Migrations created (if models changed)
- [ ] Documentation updated
- [ ] No secrets in code
- [ ] Docker build succeeds
- [ ] All tests pass
- [ ] CI checks pass

## Project Structure

```
printer-queue-service/
├── api/                 # FastAPI application
│   ├── app/
│   │   ├── api/        # API endpoints
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── middleware/ # Middleware
│   │   └── db/         # Database utilities
│   └── tests/          # API tests
├── worker/             # Celery worker
│   ├── app/
│   │   └── tasks/      # Celery tasks
│   └── tests/          # Worker tests
├── shared/             # Shared code
├── migrations/         # Alembic migrations
└── docker-compose.yml  # Docker orchestration
```

## Common Issues

### Port conflicts

If ports 8000, 5432, or 6379 are in use:

```bash
# Check what's using the port
lsof -i :8000

# Stop the service or change ports in docker-compose.yml
```

### Database connection errors

```bash
# Ensure Postgres is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Restart Postgres
docker-compose restart postgres
```

### Migration conflicts

```bash
# Check current version
docker-compose run --rm api alembic current

# Reset migrations (DANGER: drops all data)
docker-compose down -v
docker-compose up -d postgres
docker-compose run --rm api alembic upgrade head
```

## Getting Help

- Check [VALIDATION_GUIDE.md](./VALIDATION_GUIDE.md) for setup validation
- Check [README.md](./README.md) for general information
- Check [ENV_SETUP.md](./ENV_SETUP.md) for environment variables
- Open an issue for bugs or questions

## License

Proprietary - All rights reserved
