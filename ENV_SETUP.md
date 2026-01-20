# Environment Setup

Before running the project, create a `.env` file in the root directory with the following content:

```bash
# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=printer_queue
POSTGRES_PASSWORD=changeme
POSTGRES_DB=printer_queue_db

# Redis
REDIS_URL=redis://redis:6379/0

# API
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
API_WORKERS=1

# Worker
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Security
SECRET_KEY=changeme-use-a-secure-random-key-in-production

# Environment
ENVIRONMENT=development
```

## Quick Setup

Run this command to create the `.env` file:

```bash
cat > .env << 'EOF'
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=printer_queue
POSTGRES_PASSWORD=changeme
POSTGRES_DB=printer_queue_db
REDIS_URL=redis://redis:6379/0
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
API_WORKERS=1
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
SECRET_KEY=changeme-use-a-secure-random-key-in-production
ENVIRONMENT=development
EOF
```

**Note:** Never commit the `.env` file to version control. It's already added to `.gitignore`.
