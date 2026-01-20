#!/bin/bash
# Run database migrations

set -e

COMMAND=${1:-upgrade}

case $COMMAND in
  upgrade)
    echo "🔄 Running migrations..."
    docker-compose exec api bash -c "cd /migrations && alembic upgrade head"
    echo "✅ Migrations applied!"
    ;;
  
  downgrade)
    STEPS=${2:-1}
    echo "⬇️  Downgrading $STEPS step(s)..."
    docker-compose exec api bash -c "cd /migrations && alembic downgrade -$STEPS"
    echo "✅ Downgrade complete!"
    ;;
  
  current)
    echo "📋 Current migration:"
    docker-compose exec api bash -c "cd /migrations && alembic current"
    ;;
  
  history)
    echo "📚 Migration history:"
    docker-compose exec api bash -c "cd /migrations && alembic history --verbose"
    ;;
  
  create)
    if [ -z "$2" ]; then
      echo "❌ Usage: $0 create <migration_name>"
      exit 1
    fi
    echo "📝 Creating new migration: $2"
    docker-compose exec api bash -c "cd /migrations && alembic revision -m \"$2\""
    ;;
  
  *)
    echo "Usage: $0 {upgrade|downgrade|current|history|create} [args]"
    echo ""
    echo "Commands:"
    echo "  upgrade           - Apply all pending migrations"
    echo "  downgrade [n]     - Rollback n migrations (default: 1)"
    echo "  current           - Show current migration version"
    echo "  history           - Show migration history"
    echo "  create <name>     - Create new migration"
    exit 1
    ;;
esac
