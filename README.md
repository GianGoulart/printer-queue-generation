# Printer Queue Service

Sistema multi-tenant para automação de bases DTF (Direct-to-Film). Processa picklists PDF, resolve artes por SKU, aplica dimensionamento e gera bases otimizadas.

## Arquitetura

- **API**: FastAPI para endpoints REST
- **Worker**: Celery para processamento assíncrono
- **Database**: PostgreSQL com extensão pg_trgm para busca fuzzy
- **Queue**: Redis para gerenciamento de tarefas

## Quick Start

### Opção 2: Usando Make

```bash
make full-setup
```

### Opção 3: Manual

1. Criar arquivo `.env`:
```bash
cp ENV_SETUP.md .env  # Copie o conteúdo do arquivo ENV_SETUP.md
```

2. Iniciar serviços:
```bash
docker-compose up --build -d
```

3. Executar migrações:
```bash
docker-compose run --rm api alembic upgrade head
```

4. Popular banco:
```bash
docker-compose run --rm api python -m app.db.seed
```

## Pré-requisitos

- Docker (versão 20.10+)
- Docker Compose (versão 2.0+)
- Make (opcional, mas recomendado)

## Validação

### Validação Rápida

```bash
make validate
```

Ou manualmente:

### 1. Verificar Health da API

```bash
curl http://localhost:8000/health
```

Resposta esperada:
```json
{
  "status": "ok",
  "db": "connected",
  "redis": "connected"
}
```

### 2. Verificar Database

```bash
# Conectar no PostgreSQL
make shell-db
# Ou: docker-compose exec postgres psql -U printer_queue -d printer_queue_db

# Dentro do psql:
\dt                           # Listar tabelas (deve ter 8)
SELECT * FROM tenants;         # Deve ter 1 tenant demo
SELECT * FROM machines;        # Deve ter 1 máquina
SELECT * FROM sizing_profiles; # Deve ter 4 perfis (P, M, G, GG)
\d+ assets                     # Verificar índice trigram em sku_normalized
SELECT * FROM pg_extension WHERE extname = 'pg_trgm'; # Verificar extensão
\q
```

### 3. Verificar Worker

```bash
# Ver logs do worker
make logs-worker
# Ou: docker-compose logs -f worker
```

Deve mostrar: `[INFO] celery@<hostname> ready.`

### Validação Completa

Para validação completa com todos os critérios de aceite, consulte [VALIDATION_GUIDE.md](./VALIDATION_GUIDE.md).

## Estrutura do Projeto

```
printer-queue-service/
├── api/                      # FastAPI application
│   ├── app/
│   │   ├── api/             # API endpoints
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── middleware/      # Middleware (tenant, etc)
│   │   └── db/              # Database utilities and seeds
│   └── tests/
├── worker/                   # Celery worker
│   ├── app/
│   │   ├── tasks/           # Celery tasks
│   │   └── celery_app.py    # Celery configuration
│   └── tests/
├── shared/                   # Shared code
├── migrations/               # Alembic migrations
└── docker-compose.yml
```

## API Endpoints

### Fase 1 (Fundação)

- `GET /health` - Health check da API, database e Redis
- `GET /v1/tenants` - Lista tenants (para validação)

### Fase 2 (Storage e Assets)

- `GET /v1/assets` - Lista assets com paginação
- `GET /v1/assets/search` - Busca fuzzy por SKU
- `POST /v1/assets/reindex` - Reindexa assets do storage
- `GET /v1/storage/test` - Testa conexão com storage

### Fase 3 (Jobs e Picklists)

- `POST /v1/jobs` - Upload picklist PDF e cria job
- `GET /v1/jobs` - Lista jobs com paginação e filtros
- `GET /v1/jobs/{id}` - Detalhes do job
- `DELETE /v1/jobs/{id}` - Cancela/deleta job
- `GET /v1/jobs/{id}/pending-items` - Items pendentes (missing/ambiguous)
- `POST /v1/jobs/{id}/resolve` - Resolve items manualmente

## Database Schema

### Tabelas

1. **tenants** - Inquilinos do sistema
2. **machines** - Máquinas de impressão por tenant
3. **tenant_storage_configs** - Configurações de storage (S3/Dropbox/local)
4. **assets** - Artes/imagens indexadas por tenant
5. **jobs** - Jobs de processamento
6. **job_items** - Itens de cada job
7. **sizing_profiles** - Perfis de dimensionamento (P, M, G, GG)

### Seeds Iniciais

- 1 tenant demo ("Demo Tenant")
- 1 máquina (600mm x 2500mm, 300 DPI mínimo)
- 4 sizing profiles:
  - P: 80mm
  - M: 100mm
  - G: 120mm
  - GG: 140mm

## Desenvolvimento

### Comandos Úteis (via Make)

```bash
make help          # Ver todos os comandos disponíveis
make up            # Iniciar serviços
make down          # Parar serviços
make logs          # Ver logs
make logs-api      # Ver logs da API
make logs-worker   # Ver logs do Worker
make restart       # Reiniciar serviços
make shell-api     # Shell Python na API
make shell-worker  # Shell Python no Worker
make shell-db      # Shell psql no banco
make test          # Executar testes
make lint          # Executar linter
make format        # Formatar código
make migrate       # Executar migrations
make seed          # Popular banco
make clean         # Limpar tudo
```

### Rodar Testes

```bash
make test
# Ou: docker-compose run --rm api pytest
```

### Criar Nova Migration

```bash
make migrate-create MSG="description"
# Ou: docker-compose run --rm api alembic revision --autogenerate -m "description"
```

### Acessar Shells

```bash
make shell-api     # Python shell na API
make shell-worker  # Python shell no Worker
make shell-db      # psql shell no banco
```

Para mais informações sobre desenvolvimento, consulte [CONTRIBUTING.md](./CONTRIBUTING.md).

## CI/CD

O projeto utiliza GitHub Actions para:
- Lint com ruff
- Testes automatizados
- Validação de migrations

## Troubleshooting

### Containers não sobem

```bash
# Limpar tudo e reconstruir
docker-compose down -v
docker-compose up --build
```

### Erro de conexão com database

Verifique se o container do Postgres está rodando:
```bash
docker-compose ps
docker-compose logs postgres
```

### Worker não processa tasks

Verifique logs do worker e conexão com Redis:
```bash
docker-compose logs worker
docker-compose logs redis
```

## Desenvolvimento de Fases

### Fase 1: Fundação ✅ COMPLETA
- Infraestrutura base (API, Worker, Database, CI)
- 8 models SQLAlchemy
- Docker Compose com 4 serviços
- Documentação completa

### Fase 2: Storage e Indexação ✅ COMPLETA
- Drivers de storage (S3, Dropbox, Local)
- Reindexação de assets
- Busca fuzzy por SKU
- Ver **[PHASE_2_PROMPT.md](./PHASE_2_PROMPT.md)** para detalhes

### Fase 3: Ingestão de Picklist e Pipeline ✅ COMPLETA
- Upload e processamento de PDF picklist
- Parsing com Docling (Feature 6)
- Resolução automática de SKUs com fuzzy matching (Feature 7)
- Fluxo de resolução manual para SKUs ambíguos
- Ver **[PHASE_3_COMPLETE.md](./PHASE_3_COMPLETE.md)** para documentação completa

### Próximas Fases
- **Fase 4**: Dimensionamento e Layout
- **Fase 5**: Algoritmos de packing (BEST_FIT, PDF_ORDER)
- **Fase 6**: Geração de PDFs e manifesto

## Licença

Proprietário
