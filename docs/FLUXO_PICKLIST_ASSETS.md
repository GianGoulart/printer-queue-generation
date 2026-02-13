# Fluxo: upload do PDF até layout (com seus dados)

Dados de exemplo:
- **Assets** (nomes de arquivo): `unicorn-4.png`, `astrocat-g4.png`, `owl-g4.png`, `pawpatrol-2.png`, etc.
- **Sizing profiles (sku_prefix):** `inf-10`, `plus-10`, `u-14`, `plus-12`, `inf-11`, `plus-14`, `u-15`, `inf-12`
- **Picklist (linhas do PDF):** `inf-10-6-unicorn-4`, `plus-10-6-astrocat-g4`, `u-14-8-owl-g4`, etc.
- **SKU layout:** mask `{prefix}-{num1}-{num2}-{name}-{size}`

---

## Visão geral

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Upload PDF     │────▶│  Parse PDF       │────▶│  Resolve SKU    │────▶│  Sizing +       │
│  (picklist)     │     │  (layout +       │     │  (design-only + │     │  Packing +      │
│                 │     │   normaliza)     │     │   prefix → size)│     │  Render         │
└─────────────────┘     └──────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 1. Upload do PDF

- **API:** POST job com o arquivo do picklist (PDF).
- **Storage:** PDF salvo (ex.: `tenant/2/picklists/xxx.pdf`).
- **Job:** Registro criado com `picklist_uri`, `tenant_id`, `status=processing` (ou pending).
- **Worker:** Task `process_job(job_id)` é disparada.

---

## 2. Parse do PDF (leitura do layout)

- Worker baixa o PDF e carrega **tenant_layouts** (priority) e **sizing profiles** (para uso depois).
- Para **cada linha** do PDF (ex.: primeira “palavra” ou linha inteira, conforme o parser):

  **Exemplo de linha:** `inf-10-6-unicorn-4`

  1. Tenta **layout do tenant** com `full_line=True`:
     - Layout: mask `{prefix}-{num1}-{num2}-{name}-{size}`
     - Match: linha inteira bate → `full_match = "inf-10-6-unicorn-4"`.
  2. **Normalização:** `normalize_sku_from_pdf("inf-10-6-unicorn-4")` → **`inf106unicorn4`** (lowercase, sem hífens).
  3. Item do job criado com **`sku = "inf106unicorn4"`** (e quantidade se houver).

Resultado do parse para as linhas que você mandou:

| Linha no PDF              | sku (normalizado)   |
|---------------------------|----------------------|
| inf-10-6-unicorn-4        | inf106unicorn4       |
| plus-10-6-astrocat-g4     | plus106astrocatg4    |
| u-14-8-owl-g4             | u148owlg4            |
| inf-10-14-pawpatrol-2     | inf1014pawpatrol2    |
| plus-12-7-panda-g3        | plus127pandag3       |
| u-14-9-coffee-gg          | u149coffeegg         |
| …                         | …                    |

---

## 3. Resolução de SKU (achar o asset)

Para cada **item.sku** (ex.: `inf106unicorn4`):

1. **Candidatos para lookup:**  
   Com **sizing_prefixes** = `["inf10", "plus10", "u14", "plus12", "inf11", "plus14", "u15", "inf12"]` (normalizados):
   - SKU completo: `inf106unicorn4`
   - Depois de tirar prefixo `inf10`: resto `6unicorn4` → **design** (tirar “6” na frente): **`unicorn4`**

2. **Ordem de tentativa:**  
   - Exact match em `inf106unicorn4` → nenhum asset tem esse sku_normalized.  
   - Exact match em `6unicorn4` → nenhum.  
   - Exact match em **`unicorn4`** → **encontra** o asset cujo arquivo é **`unicorn-4.png`** (no reindex esse arquivo vira `sku_normalized = "unicorn4"`).

3. **Resultado:** item fica **resolved** com `asset_id` = id do asset `unicorn-4.png`.

Fluxo do resolver (resumo):

```
item.sku = "inf106unicorn4"
    │
    ├─ exact("inf106unicorn4")     → não acha
    ├─ exact("6unicorn4")          → não acha
    └─ exact("unicorn4")           → acha asset "unicorn-4.png"  ✓
```

Como os **assets** estão nomeados só pelo “design + size” (ex.: `unicorn-4.png`, `owl-g4.png`), no **reindex** com **sizing_prefixes** do tenant:
- Não há prefixo no início de `unicorn-4.png` → nada é tirado no início.
- `extract_sku("unicorn-4.png", sizing_prefixes=[...])` → **`unicorn4`** (só normalização).
- Então o asset fica com **sku_normalized = "unicorn4"**, que é exatamente o “design” que o resolver obtém ao tirar o prefixo da picklist.

---

## 4. Sizing (escolher tamanho pelo prefixo)

- Para cada item **resolved**, o worker pega **item.sku** (ex.: `inf106unicorn4`) e compara com os **sku_prefix** dos sizing profiles (normalizados):
  - `inf106unicorn4`.startswith("inf10") → **sim** → usa o perfil **inf-10** (ex.: Infantil 10, target_width_mm X).
- Esse perfil define a “base” (largura alvo, etc.) para aquele item.

---

## 5. Resumo em tabela (um exemplo por linha)

| Picklist (PDF)           | sku normalizado   | Prefixo (sizing) | Design (lookup asset) | Asset (arquivo)   | Sizing profile |
|--------------------------|------------------|------------------|------------------------|-------------------|----------------|
| inf-10-6-unicorn-4       | inf106unicorn4   | inf10            | unicorn4                | unicorn-4.png     | inf-10         |
| plus-10-6-astrocat-g4     | plus106astrocatg4| plus10           | 6astrocatg4 → astrocatg4| astrocat-g4.png   | plus-10        |
| u-14-8-owl-g4            | u148owlg4        | u14              | 8owlg4 → owlg4          | owl-g4.png        | u-14           |
| inf-10-14-pawpatrol-2    | inf1014pawpatrol2| inf10            | 14pawpatrol2 → pawpatrol2 | pawpatrol-2.png | inf-10         |
| plus-12-7-panda-g3       | plus127pandag3   | plus12           | 7pandag3 → pandag3      | panda-g3.png      | plus-12        |
| u-14-9-coffee-gg         | u149coffeegg     | u14              | 9coffeegg → coffeegg    | coffee-gg.png     | u-14           |
| inf-11-15-hulk-10       | inf1115hulk10    | inf11            | 15hulk10 → hulk10       | hulk-10.png       | inf-11         |
| plus-14-8-owl-g4         | plus148owlg4     | plus14           | 8owlg4 → owlg4          | owl-g4.png        | plus-14        |
| u-15-10-dragon-m         | u1510dragonm     | u15              | 10dragonm → dragonm     | dragon-m.png      | u-15           |
| inf-12-13-sonic-8       | inf1213sonic8    | inf12            | 13sonic8 → sonic8       | sonic-8.png       | inf-12         |

*(Design “Xy” na tabela é o que sobra depois de tirar o prefixo e o segmento numérico inicial; o resolver tenta também o resto sem tirar o número, e o asset pode estar como "owl-g4" → "owlg4" ou "owl-g4" sem strip → depende do que você tiver no reindex.)*

---

## 6. Condições para esse fluxo funcionar

1. **Reindex dos assets** com **sizing_prefixes** do tenant carregados, para que:
   - `unicorn-4.png` → `sku_normalized = "unicorn4"`
   - `owl-g4.png` → `sku_normalized = "owlg4"`
   - etc.  
   (Nenhum prefixo do tenant no início desses nomes → só normalização.)

2. **Sizing profiles** com **sku_prefix** preenchido (inf-10, plus-10, u-14, etc.) para o mesmo tenant.

3. **SKU layout** ativo com mask `{prefix}-{num1}-{num2}-{name}-{size}` e prioridade menor que outros layouts, para as linhas do picklist baterem nesse formato.

4. **Resolver** recebendo **sizing_prefixes** (feito no process_job) para fazer o “design-only” lookup e achar o asset pelo design (ex.: unicorn4, owlg4).

---

## 7. Diagrama linear (do upload ao render)

```
Upload PDF
    │
    ▼
Job criado (picklist_uri, tenant_id)
    │
    ▼
process_job(job_id)
    │
    ├─ 1. Download PDF
    ├─ 2. Carregar tenant_layouts + sizing_prefixes (sizing profiles)
    │
    ├─ 3. PARSE PDF
    │      Por linha:
    │        • match layout {prefix}-{num1}-{num2}-{name}-{size}
    │        • full_match → normalize_sku_from_pdf → item.sku (ex.: inf106unicorn4)
    │
    ├─ 4. RESOLVE (por item)
    │      resolve_sku(item.sku, tenant_id, db, sizing_prefixes)
    │        • tenta exact(full), exact(resto), exact(design)
    │        • design = resto após prefixo, sem número no início (ex.: unicorn4)
    │        • asset com sku_normalized = design → item.asset_id, status=resolved
    │
    ├─ 5. SIZING (por item resolved)
    │      item.sku.startswith(prefix) → SizingProfile (target_width_mm, etc.)
    │
    ├─ 6. PACKING + RENDER
    │      (usa asset + sizing para gerar saída)
    │
    └─ Job concluído (ou needs_input se faltar asset)
```

Com isso, o fluxo desde o upload do PDF até o layout fica determinado pelos dados que você descreveu (assets, sku_prefixes, picklist e sku_layout).

---

## Validação do código (checklist)

| Etapa | Onde | Verificado |
|-------|------|------------|
| **1. Carregar layouts do tenant** | `process_job.py` L115–136 | ✅ `SkuLayout` filtrado por `tenant_id`, `active=True`, ordenado por `priority.asc()`; monta `tenant_layouts` com `id`, `name`, `pattern`, `pattern_type`, `allow_hyphen_variants`. |
| **2. Parser usa layout com full_line** | `robust_pdf_parser.py` L697–725 | ✅ Para cada linha, `line_first_token` = primeiro token (ex.: `inf-10-6-unicorn-4`); `find_matches(..., full_line=True)`; em match, `sku = normalize_sku_from_pdf(full_match)` → ex.: `inf106unicorn4`. |
| **3. Normalização igual ao catálogo** | `robust_pdf_parser.py` L253–283 | ✅ `normalize_sku_from_pdf`: lowercase, remove `- _ ` e extensão; mesmo critério do `sku_resolver.normalize_sku` e `sku_extractor.normalize_sku`. |
| **4. JobItem com sku do parse** | `process_job.py` L174–189 | ✅ `JobItem(sku=parsed_item.sku, ...)`; `parsed_item.sku` vem de `PicklistItem(sku=sku_with_qty.sku)` que vem do `match.sku` (já normalizado). |
| **5. Carregar sizing_prefixes para resolver** | `process_job.py` L213–226 | ✅ `SizingProfile` com `tenant_id` e `sku_prefix` não nulo; `sizing_prefixes = [p.sku_prefix.lower().replace("-","").strip() ...]`. |
| **6. Resolver com design-only** | `sku_resolver.py` L56–77, L46–54 | ✅ `_candidate_skus_for_lookup`: full SKU + para cada prefixo (maior primeiro) resto e `_design_from_remainder(resto)`; tenta exact(candidate) depois fuzzy(candidate). |
| **7. Strip de número no design** | `sku_resolver.py` L46–54 | ✅ `_design_from_remainder`: remove `^[0-9]+[-_]?` do início (ex.: `6unicorn4` → `unicorn4`). |
| **8. Sizing por prefixo no item.sku** | `process_job.py` L504–513 | ✅ `sku_normalized = item.sku.lower().replace("-","")`; `sorted_prefixes` por length desc; `if sku_normalized.startswith(prefix)` → usa esse `SizingProfile`. |
| **9. Reindex usa sizing_prefixes** | `reindex.py` L169–208 | ✅ Carrega `SizingProfile` do tenant, monta `sizing_prefixes`; `extract_sku(filename, sizing_prefixes=sizing_prefixes)`; assets como `unicorn-4.png` (sem prefixo no nome) → `sku_normalized = "unicorn4"`. |

Conclusão: o código cobre o fluxo descrito (parse com layout → sku normalizado → resolução por design + prefixos de sizing → sizing por prefixo; reindex com prefixos do tenant para assets “só design”).
