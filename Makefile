.PHONY: help setup up down build restart logs clean migrate seed test lint format validate

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Initial setup - create .env file
	@echo "Creating .env file..."
	@cat > .env << 'EOF'\
	POSTGRES_HOST=postgres\
	POSTGRES_PORT=5432\
	POSTGRES_USER=printer_queue\
	POSTGRES_PASSWORD=changeme\
	POSTGRES_DB=printer_queue_db\
	REDIS_URL=redis://redis:6379/0\
	API_HOST=0.0.0.0\
	API_PORT=8000\
	API_RELOAD=true\
	API_WORKERS=1\
	CELERY_BROKER_URL=redis://redis:6379/0\
	CELERY_RESULT_BACKEND=redis://redis:6379/0\
	SECRET_KEY=changeme-use-a-secure-random-key-in-production\
	ENVIRONMENT=development\
	EOF
	@echo "✓ .env file created"

up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

build: ## Build all Docker images
	docker-compose build

restart: ## Restart all services
	docker-compose restart

logs: ## Show logs from all services
	docker-compose logs -f

logs-api: ## Show API logs
	docker-compose logs -f api

logs-worker: ## Show worker logs
	docker-compose logs -f worker

logs-db: ## Show database logs
	docker-compose logs -f postgres

clean: ## Clean all containers, volumes and images
	docker-compose down -v
	docker system prune -f

migrate: ## Run database migrations
	docker-compose run --rm --workdir /migrations api alembic upgrade head

migrate-down: ## Rollback last migration
	docker-compose run --rm --workdir /migrations api alembic downgrade -1

migrate-create: ## Create new migration (use MSG="description")
	docker-compose run --rm --workdir /migrations api alembic revision --autogenerate -m "$(MSG)"

seed: ## Seed database with initial data
	docker-compose run --rm api python -m app.db.seed

test: ## Run all tests
	docker-compose run --rm api pytest

test-api: ## Run API tests only
	docker-compose run --rm api pytest tests/

lint: ## Run linter
	docker-compose run --rm api ruff check app/
	docker-compose run --rm worker ruff check app/

format: ## Format code
	docker-compose run --rm api black app/
	docker-compose run --rm worker black app/

shell-api: ## Open Python shell in API container
	docker-compose run --rm api python

shell-worker: ## Open Python shell in Worker container
	docker-compose run --rm worker python

shell-db: ## Open psql shell in database
	docker-compose exec postgres psql -U printer_queue -d printer_queue_db

validate: ## Run full validation
	@echo "Running full validation..."
	@echo "\n1. Testing API health..."
	@curl -f http://localhost:8000/health || (echo "❌ Health check failed" && exit 1)
	@echo "\n✓ Health check passed"
	@echo "\n2. Checking pg_trgm extension..."
	@docker-compose exec -T postgres psql -U printer_queue -d printer_queue_db -c "SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';" | grep pg_trgm || (echo "❌ pg_trgm not found" && exit 1)
	@echo "✓ pg_trgm extension found"
	@echo "\n3. Checking tables..."
	@docker-compose exec -T postgres psql -U printer_queue -d printer_queue_db -c "\dt" | grep tenants || (echo "❌ Tables not found" && exit 1)
	@echo "✓ Tables found"
	@echo "\n4. Checking seeds..."
	@docker-compose exec -T postgres psql -U printer_queue -d printer_queue_db -c "SELECT COUNT(*) FROM tenants;" | grep 1 || (echo "❌ Seeds not applied" && exit 1)
	@echo "✓ Seeds applied"
	@echo "\n✓ All validations passed!"

full-setup: setup build up migrate seed ## Complete setup from scratch
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "✓ Setup complete! API available at http://localhost:8000"
	@echo "✓ Run 'make validate' to verify installation"

full-reset: clean full-setup ## Complete reset and setup
	@echo "✓ Full reset complete!"
