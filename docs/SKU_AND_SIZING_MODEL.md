# Modelo de SKU e Sizing (prefixo = tamanho, asset = design)

## Onde está a lista de sufixos

- **Arquivo:** `api/app/services/sku_extractor.py`
- **Constantes:**
  - **`SIZE_SUFFIXES`** (linhas 8–12): P, M, G, GG, XG, PP, S, L, XL, XXL, XXXL, 1–6 — usados para remover **só no final** do nome ao extrair SKU do filename.
  - **`POSITION_SUFFIXES`** (linhas 14–19): FRENTE, COSTAS, etc. — removidos no final.

Só o que está nessas listas é removido (e apenas como sufixo final). Ex.: `-10` não está na lista → fica em `inf58mario10`.

---

## Sua lógica (correção / resumo)

1. **Assets** = identificados só pelo **design** (+ sufixo de tamanho do produto se quiser):
   - `bl-7-4-butterfly-p.png` → **sku_normalized no asset:** `butterflyp` (ou `butterfly-p` normalizado)
   - `inf-10-pawpatrol-2.png` → **sku_normalized no asset:** `pawpatrol2` (ou `pawpatrol-2` normalizado)

2. **Sizing profile** = definido pelo **prefixo** do SKU (já existe no sistema):
   - Perfil com **sku_prefix** `bl-7` → tamanho X (target_width_mm, size_label).
   - Perfil com **sku_prefix** `inf-10` → tamanho Y.

3. **Picklist** vem com SKU completo, ex.:
   - `bl-7-4-butterfly-p` → identificamos o **asset** por `butterfly-p` (design) e o **tamanho** pelo prefixo `bl-7`.
   - `inf-10-14-pawpatrol-2` (ou `inf-10-pawpatrol-2`) → asset `pawpatrol-2`, tamanho pelo prefixo `inf-10`.

Fluxo:

- Da picklist: `bl-7-4-butterfly-p` ou `inf-10-pawpatrol-2`.
- Extrair **prefixo** (bl-7, inf-10) → buscar **sizing profile** por `sku_prefix` → define a base (tamanho).
- Extrair **design** (butterfly-p, pawpatrol-2) → buscar **asset** por esse SKU normalizado (ex.: `butterflyp`, `pawpatrol2`).

Isso está alinhado com o que você descreveu.

---

## O que o código já faz

- **Sizing profile por prefixo:** em `worker/app/tasks/process_job.py` (por volta das linhas 441–498) já existe:
  - Mapa de `sku_prefix` (normalizado, ex.: `bl7`, `inf10`) → `SizingProfile`.
  - Para cada item resolvido, `item.sku` é normalizado e faz-se `sku_normalized.startswith(prefix)`; o perfil do prefixo que bater define o tamanho (e a “base”).

Ou seja: **atribuir tamanho pelo prefixo usando sizing profile já está implementado.**

---

## Implementação: resolver por design quando há sizing prefixes

Implementado em:

- **`worker/app/services/sku_resolver.py`**  
  - `resolve_sku(..., sizing_prefixes=None)`  
  - Se `sizing_prefixes` for passado (ex.: `['bl7','inf10']`), após tentar o SKU completo o resolver tira cada prefixo (mais longo primeiro) e tenta: **remainder** (ex.: `4butterflyp`) e **design** (ex.: `butterflyp` = remainder sem segmento numérico inicial). Assim, picklist `bl-7-4-butterfly-p` → normalizado `bl74butterflyp` → tenta `bl74butterflyp`, depois `4butterflyp`, depois `butterflyp` → encontra asset com `sku_normalized = butterflyp`.

- **`worker/app/tasks/process_job.py`**  
  - Antes do loop de resolução, carrega os sizing profiles do tenant e monta a lista de `sku_prefix` normalizados (ex.: `bl-7` → `bl7`).  
  - Chama `resolver.resolve_sku(item.sku, job.tenant_id, db, sizing_prefixes=sizing_prefixes)`.

Nos **assets**, mantenha `sku_normalized` só com o design (ex.: `butterflyp`, `pawpatrol2`). O **tamanho** continua a ser definido pelo prefixo do **item.sku** (ex.: `bl-7`) na fase de sizing (Feature 8), que já faz o match por prefixo.
