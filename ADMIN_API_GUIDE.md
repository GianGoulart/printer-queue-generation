# 🔧 API de Administração - Guia Completo

Guia para gerenciar tenants, máquinas, sizing profiles e configurações de storage via REST API.

---

## 📋 Índice

1. [Tenants](#tenants)
2. [Machines](#machines)
3. [Sizing Profiles](#sizing-profiles)
4. [Storage Configs](#storage-configs)

---

## 🏢 Tenants

### Listar Todos os Tenants

```bash
# Apenas tenants ativos
curl "http://localhost:8000/v1/tenants"

# Incluir inativos
curl "http://localhost:8000/v1/tenants?include_inactive=true"
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Demo Tenant",
    "is_active": true,
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-15T10:00:00Z"
  }
]
```

---

### Criar Novo Tenant

```bash
curl -X POST "http://localhost:8000/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Tenant Test 2"
  }'
```

**Response:**
```json
{
  "id": 2,
  "name": "Tenant Test 2",
  "is_active": true,
  "created_at": "2026-01-17T10:00:00Z",
  "updated_at": "2026-01-17T10:00:00Z"
}
```

---

### Obter Tenant por ID

```bash
curl "http://localhost:8000/v1/tenants/2"
```

---

### Atualizar Tenant

```bash
curl -X PUT "http://localhost:8000/v1/tenants/2" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Tenant Updated",
    "is_active": false
  }'
```

---

## 🖨️ Machines

### Listar Máquinas do Tenant

```bash
curl "http://localhost:8000/v1/machines" \
  -H "X-Tenant-ID: 2"
```

**Response:**
```json
[
  {
    "id": 2,
    "tenant_id": 2,
    "name": "DTF Printer Test",
    "max_width_mm": 600.0,
    "max_length_mm": 2500.0,
    "min_dpi": 300,
    "created_at": "2026-01-17T10:00:00Z"
  }
]
```

---

### Criar Nova Máquina

```bash
curl -X POST "http://localhost:8000/v1/machines" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DTF Printer Test",
    "max_width_mm": 600,
    "max_length_mm": 2500,
    "min_dpi": 300
  }'
```

**Nota:** O `tenant_id` é automaticamente obtido do header `X-Tenant-ID`.

**Response:**
```json
{
  "id": 2,
  "tenant_id": 2,
  "name": "DTF Printer Test",
  "max_width_mm": 600.0,
  "max_length_mm": 2500.0,
  "min_dpi": 300,
  "created_at": "2026-01-17T10:00:00Z"
}
```

---

### Obter Máquina por ID

```bash
curl "http://localhost:8000/v1/machines/2" \
  -H "X-Tenant-ID: 2"
```

---

### Atualizar Máquina

```bash
curl -X PUT "http://localhost:8000/v1/machines/2" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DTF Printer Updated",
    "max_width_mm": 650,
    "min_dpi": 350
  }'
```

---

### Deletar Máquina

```bash
curl -X DELETE "http://localhost:8000/v1/machines/2" \
  -H "X-Tenant-ID: 2"
```

---

## 📏 Sizing Profiles

### Listar Sizing Profiles do Tenant

```bash
curl "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2"
```

**Response:**
```json
[
  {
    "id": 5,
    "tenant_id": 2,
    "size_label": "P",
    "target_width_mm": 80.0,
    "created_at": "2026-01-17T10:00:00Z"
  },
  {
    "id": 6,
    "tenant_id": 2,
    "size_label": "M",
    "target_width_mm": 100.0,
    "created_at": "2026-01-17T10:00:00Z"
  }
]
```

---

### Criar Sizing Profile

```bash
curl -X POST "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "size_label": "P",
    "target_width_mm": 80
  }'
```

**Nota:** O `tenant_id` é automaticamente obtido do header `X-Tenant-ID`.

---

### Criar Múltiplos Sizing Profiles

```bash
# P
curl -X POST "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{"size_label": "P", "target_width_mm": 80}'

# M
curl -X POST "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{"size_label": "M", "target_width_mm": 100}'

# G
curl -X POST "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{"size_label": "G", "target_width_mm": 120}'

# GG
curl -X POST "http://localhost:8000/v1/sizing-profiles" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{"size_label": "GG", "target_width_mm": 140}'
```

---

### Obter Sizing Profile por ID

```bash
curl "http://localhost:8000/v1/sizing-profiles/5" \
  -H "X-Tenant-ID: 2"
```

---

### Atualizar Sizing Profile

```bash
curl -X PUT "http://localhost:8000/v1/sizing-profiles/5" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "target_width_mm": 85
  }'
```

---

### Deletar Sizing Profile

```bash
curl -X DELETE "http://localhost:8000/v1/sizing-profiles/5" \
  -H "X-Tenant-ID: 2"
```

---

## 💾 Storage Configs

### Obter Configuração de Storage

```bash
curl "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2"
```

**Response:**
```json
{
  "id": 2,
  "tenant_id": 2,
  "provider": "local",
  "base_path": "/tmp/printer-queue-assets/tenant-2",
  "created_at": "2026-01-17T10:00:00Z",
  "updated_at": "2026-01-17T10:00:00Z"
}
```

---

### Criar Storage Config (Local)

```bash
curl -X POST "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "local",
    "base_path": "/tmp/printer-queue-assets/tenant-2"
  }'
```

**Nota:** O `tenant_id` é automaticamente obtido do header `X-Tenant-ID`.

---

### Criar Storage Config (S3)

```bash
curl -X POST "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "s3",
    "base_path": "my-bucket/tenant-2"
  }'
```

**Nota:** Credenciais S3 devem ser configuradas via variáveis de ambiente ou sistema de secrets.

---

### Criar Storage Config (Dropbox)

```bash
curl -X POST "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "dropbox",
    "base_path": "/tenant-2"
  }'
```

**Nota:** Credenciais Dropbox devem ser configuradas via variáveis de ambiente ou sistema de secrets.

---

### Atualizar Storage Config

```bash
curl -X PUT "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "base_path": "/new/path/tenant-2"
  }'
```

---

### Deletar Storage Config

```bash
curl -X DELETE "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: 2"
```

---

## 🚀 Setup Completo de Tenant via API

Script bash para criar um tenant completo:

```bash
#!/bin/bash

# 1. Criar Tenant
TENANT_RESPONSE=$(curl -s -X POST "http://localhost:8000/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name": "Tenant Test 2"}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.id')
echo "✓ Tenant criado: ID $TENANT_ID"

# 2. Criar Storage Config (tenant_id vem do header automaticamente)
curl -s -X POST "http://localhost:8000/v1/storage-configs" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"provider\": \"local\",
    \"base_path\": \"/tmp/printer-queue-assets/tenant-$TENANT_ID\"
  }" | jq
echo "✓ Storage config criado"

# 3. Criar Machine (tenant_id vem do header automaticamente)
MACHINE_RESPONSE=$(curl -s -X POST "http://localhost:8000/v1/machines" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"DTF Printer Test\",
    \"max_width_mm\": 600,
    \"max_length_mm\": 2500,
    \"min_dpi\": 300
  }")

MACHINE_ID=$(echo "$MACHINE_RESPONSE" | jq -r '.id')
echo "✓ Machine criada: ID $MACHINE_ID"

# 4. Criar Sizing Profiles (tenant_id vem do header automaticamente)
for size in "P:80" "M:100" "G:120" "GG:140"; do
  LABEL=$(echo $size | cut -d: -f1)
  WIDTH=$(echo $size | cut -d: -f2)
  
  curl -s -X POST "http://localhost:8000/v1/sizing-profiles" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "Content-Type: application/json" \
    -d "{
      \"size_label\": \"$LABEL\",
      \"target_width_mm\": $WIDTH
    }" > /dev/null
  
  echo "✓ Sizing profile criado: $LABEL ($WIDTH mm)"
done

# 5. Criar diretório de storage
mkdir -p "/tmp/printer-queue-assets/tenant-$TENANT_ID"/{assets,picklists,outputs}
echo "✓ Diretório de storage criado"

echo ""
echo "=========================================="
echo "✅ TENANT SETUP COMPLETO"
echo "=========================================="
echo "Tenant ID: $TENANT_ID"
echo "Machine ID: $MACHINE_ID"
echo "Storage: /tmp/printer-queue-assets/tenant-$TENANT_ID"
echo ""
echo "Pronto para usar!"
```

---

## 📝 Resumo dos Endpoints

| Recurso | Método | Endpoint | Descrição |
|---------|--------|----------|-----------|
| Tenants | GET | `/v1/tenants` | Listar tenants |
| | POST | `/v1/tenants` | Criar tenant |
| | GET | `/v1/tenants/{id}` | Obter tenant |
| | PUT | `/v1/tenants/{id}` | Atualizar tenant |
| Machines | GET | `/v1/machines` | Listar máquinas |
| | POST | `/v1/machines` | Criar máquina |
| | GET | `/v1/machines/{id}` | Obter máquina |
| | PUT | `/v1/machines/{id}` | Atualizar máquina |
| | DELETE | `/v1/machines/{id}` | Deletar máquina |
| Sizing Profiles | GET | `/v1/sizing-profiles` | Listar profiles |
| | POST | `/v1/sizing-profiles` | Criar profile |
| | GET | `/v1/sizing-profiles/{id}` | Obter profile |
| | PUT | `/v1/sizing-profiles/{id}` | Atualizar profile |
| | DELETE | `/v1/sizing-profiles/{id}` | Deletar profile |
| Storage Configs | GET | `/v1/storage-configs` | Obter config |
| | POST | `/v1/storage-configs` | Criar config |
| | PUT | `/v1/storage-configs` | Atualizar config |
| | DELETE | `/v1/storage-configs` | Deletar config |

---

## ✨ Benefícios

✅ **Não precisa mais de SQL direto** - Tudo via REST API  
✅ **Validação automática** - Checks de tenant_id, duplicatas, etc.  
✅ **Multi-tenant seguro** - X-Tenant-ID header previne cross-tenant access  
✅ **Documentação OpenAPI** - Acesse `/docs` para testar interativamente  
✅ **Type-safe** - Pydantic schemas garantem validação de dados  

---

Para ver a documentação interativa completa: **http://localhost:8000/docs**
