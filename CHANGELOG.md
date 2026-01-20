# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-01-14

### Added - Fase 1: Fundação

#### Infrastructure
- Docker Compose configuration with 4 services (Postgres, Redis, API, Worker)
- Dockerfiles for API and Worker with multi-stage builds
- GitHub Actions CI with lint, tests and migrations validation
- Makefile with 25+ useful commands
- Quick start script for automated setup

#### API (FastAPI)
- FastAPI application with CORS and documentation
- Configuration via pydantic-settings with .env support
- SQLAlchemy 2.0+ with connection pooling
- Health check endpoint (`/health`) with DB and Redis status
- Tenant middleware for multi-tenancy support
- Endpoints:
  - `GET /health` - Complete health check
  - `GET /v1/healthz` - Simple health check
  - `GET /v1/tenants` - List tenants

#### Database (PostgreSQL)
- 8 SQLAlchemy models:
  - Tenant
  - Machine
  - TenantStorageConfig
  - Asset
  - Job
  - JobItem
  - SizingProfile
- Alembic migrations setup
- Initial migration with all tables
- pg_trgm extension for fuzzy search
- Trigram GIN index on assets.sku_normalized
- Optimized indexes on FKs and frequently queried fields

#### Worker (Celery)
- Celery configuration with Redis broker
- Auto-discovery of tasks
- Example tasks (dummy_task, health_check)
- Timeout and concurrency configuration

#### Data
- Database seeding script
- Initial data:
  - 1 Demo Tenant
  - 1 Demo Machine (600mm x 2500mm, 300 DPI)
  - 4 Sizing Profiles (P: 80mm, M: 100mm, G: 120mm, GG: 140mm)

#### Testing
- Pytest configuration
- Test fixtures for database and client
- Health endpoint tests
- CI integration

#### Documentation
- README.md with quick start guide
- VALIDATION_GUIDE.md with complete validation steps
- CONTRIBUTING.md with development guide
- ENV_SETUP.md with environment configuration
- PHASE_1_COMPLETION.md with implementation summary
- API documentation via FastAPI (Swagger/ReDoc)

#### Code Quality
- Ruff for linting
- Black for formatting
- Configuration files (ruff.toml, pyproject.toml)
- .gitignore and .dockerignore

### Changed
- N/A (initial release)

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- Environment variables via .env (not committed)
- Credentials encrypted field in storage configs
- PostgreSQL with strong password support

## [0.0.0] - 2026-01-14

### Added
- Initial project structure
- Documentation files:
  - Agent_Prompt_Template.md
  - API_Contract.md
  - Implementation_Roadmap.md
  - MVP_Backlog.md

---

## Version History

- **0.1.0** - Fase 1: Fundação (API + Worker + Database + CI)
- **0.0.0** - Project initialization and planning

## Next Release (Planned)

### [0.2.0] - Fase 2: Storage Drivers
- S3 storage driver
- Dropbox storage driver
- Local filesystem driver
- Asset reindexing endpoint
- Storage configuration management

### [0.3.0] - Fase 3: Picklist Parsing
- Docling integration
- PDF parsing
- Item extraction
- SKU normalization

### [0.4.0] - Fase 4: SKU Resolution
- Fuzzy SKU matching using pg_trgm
- Size label detection
- Asset resolution
- needs_input status handling

### [0.5.0] - Fase 5: Packing Algorithms
- BEST_FIT algorithm
- PDF_ORDER algorithm
- Multi-base generation
- Position calculation

### [0.6.0] - Fase 6: PDF Generation
- Base PDF generation
- Preview generation
- Manifest creation
- Job completion
