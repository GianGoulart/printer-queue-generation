### Contrato de API — MVP (Assíncrono, Multi-tenant)

#### Convenções gerais
- **Auth**: `Authorization: Bearer <token>`
- **Tenant**: token resolve `tenant_id` no servidor (evitar confiar em header fornecido pelo cliente).
- **Respostas**: JSON.
- **Processamento**: assíncrono via fila.

---

## 1) Criar Job
### `POST /v1/jobs`
**Content-Type**: `multipart/form-data`

**Campos (form-data)**
- `file` (PDF, obrigatório)
- `machine_id` (UUID, obrigatório)
- `optimization_mode` (string, obrigatório): `BEST_FIT` | `PDF_ORDER`
- `allow_rotate` (boolean, opcional; default `false`)
- `sequence_policy` (string, opcional; default `strict`): `strict` | `window`
- `sequence_window` (int, opcional; default `0`) — usado se `sequence_policy=window`
- `priority` (int, opcional; default `0`)

**Resposta**: `202 Accepted`
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-01-13T23:45:00Z",
  "links": {
    "self": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Erros**
- `400` arquivo inválido
- `413` arquivo muito grande
- `422` parâmetros inválidos

---

## 2) Consultar Job (status + outputs + pendências)
### `GET /v1/jobs/{job_id}`

**Resposta — SUCCEEDED**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "metrics": {
    "total_items": 45,
    "items_found": 45,
    "total_bases": 2,
    "processing_time_sec": 18.4
  },
  "outputs": {
    "print_files": [
      "https://storage.example.com/tenant/t1/jobs/uuid/base_1.pdf",
      "https://storage.example.com/tenant/t1/jobs/uuid/base_2.pdf"
    ],
    "previews": [
      "https://storage.example.com/tenant/t1/jobs/uuid/preview_1.jpg",
      "https://storage.example.com/tenant/t1/jobs/uuid/preview_2.jpg"
    ],
    "manifest": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000/manifest"
  }
}
```

**Resposta — NEEDS_INPUT (SKU não encontrado)**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "needs_input",
  "pending_items": [
    {
      "sku": "s-6-1-furious4-m",
      "quantity": 2,
      "size_label": "M",
      "reason": "SKU_NOT_FOUND_IN_ASSETS"
    }
  ],
  "actions": {
    "resolve_url": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000/resolve"
  }
}
```

**Resposta — FAILED**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": {
    "code": "LOW_DPI" ,
    "message": "Arte com baixa resolução / DPI insuficiente"
  }
}
```

---

## 3) Resolver pendências
### `POST /v1/jobs/{job_id}/resolve`
**Content-Type**: `application/json`

**Payload**
```json
{
  "resolutions": [
    {
      "sku": "s-6-1-furious4-m",
      "action": "use_existing_asset",
      "asset_id": "7f4d0a7c-9db6-4d46-9b07-8c3c7f2b2b01"
    },
    {
      "sku": "outro-sku",
      "action": "skip_item"
    }
  ]
}
```

**Semântica**
- `use_existing_asset`: amarra SKU ao asset escolhido.
- `skip_item`: remove o item do job (registrar no manifesto).

**Resposta**: `202 Accepted`
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

---

## 4) Manifesto
### `GET /v1/jobs/{job_id}/manifest`

**Resposta**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "machine": {
    "usable_width_mm": 600,
    "max_length_mm": 2500
  },
  "params": {
    "optimization_mode": "BEST_FIT",
    "allow_rotate": false,
    "sequence_policy": "strict",
    "sequence_window": 0
  },
  "bases": [
    {
      "base_index": 1,
      "pdf_url": "https://storage.example.com/tenant/t1/jobs/uuid/base_1.pdf",
      "preview_url": "https://storage.example.com/tenant/t1/jobs/uuid/preview_1.jpg",
      "items": [
        {
          "sku": "s-6-1-furious4-m",
          "asset_id": "7f4d0a7c-9db6-4d46-9b07-8c3c7f2b2b01",
          "quantity": 1,
          "pos_x_mm": 10,
          "pos_y_mm": 10,
          "final_width_mm": 280,
          "final_height_mm": 320,
          "rotated": false,
          "scale_applied": 0.95,
          "warnings": ["SCALED_DOWN_TO_FIT_WIDTH"]
        }
      ]
    }
  ],
  "warnings": [],
  "errors": []
}
```

---

## 5) Reindexação de assets
### `POST /v1/assets/reindex`

**Resposta**
```json
{
  "status": "sync_started"
}
```
