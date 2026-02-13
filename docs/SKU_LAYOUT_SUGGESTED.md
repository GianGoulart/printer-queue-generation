# SKU layouts sugeridos para picklist (tenant)

Para o job encontrar os SKUs na leitura do PDF, use **dois layouts em mask** (prioridade: 5 segmentos primeiro, depois 4). O parser tenta os layouts do tenant **antes** dos regex embutidos e usa **full_line=True**, então cada linha deve bater inteira em um único layout.

---

## 1. Layout 5 segmentos (prefix-num-num-name-size)

Cobre a maioria dos itens: `s-6-3-wolf-g4`, `bl-7-4-butterfly-p`, `inf-9-4-naruto-m`, `u-11-8-moonsun-p`, `m-1-6-unicorn-4`, `plus-6-3-wolf-g4`, etc.

| Campo | Valor |
|-------|--------|
| **name** | `Picklist 5 segmentos (prefix-num-num-name-size)` |
| **pattern_type** | `mask` |
| **pattern** | `{prefix}-{num1}-{num2}-{name}-{size}` |
| **priority** | `0` (primeiro a ser tentado) |
| **active** | `true` |
| **allow_hyphen_variants** | `true` |
| **example_samples** | `["s-6-3-wolf-g4", "bl-7-4-butterfly-p", "u-11-8-moonsun-p", "inf-9-4-naruto-m"]` |

---

## 2. Layout 4 segmentos (prefix-num-num-name)

Cobre itens sem sufixo de tamanho no final: `bl-13-9-flamingo`, `inf-10-14-pawpatrol-2` (se vier sem último segmento em algumas linhas).

| Campo | Valor |
|-------|--------|
| **name** | `Picklist 4 segmentos (prefix-num-num-name)` |
| **pattern_type** | `mask` |
| **pattern** | `{prefix}-{num1}-{num2}-{name}` |
| **priority** | `1` |
| **active** | `true` |
| **allow_hyphen_variants** | `true` |
| **example_samples** | `["bl-13-9-flamingo", "inf-10-14-pawpatrol"]` |

---

## Como criar (API)

**GET** `/v1/tenants/{tenant_id}/sku-layouts` para listar; **POST** `/v1/tenants/{tenant_id}/sku-layouts` para criar.

**Corpo para o layout 5 segmentos:**

```json
{
  "name": "Picklist 5 segmentos (prefix-num-num-name-size)",
  "pattern_type": "mask",
  "pattern": "{prefix}-{num1}-{num2}-{name}-{size}",
  "priority": 0,
  "active": true,
  "allow_hyphen_variants": true,
  "example_samples": ["s-6-3-wolf-g4", "bl-7-4-butterfly-p", "u-11-8-moonsun-p", "inf-9-4-naruto-m"]
}
```

**Corpo para o layout 4 segmentos:**

```json
{
  "name": "Picklist 4 segmentos (prefix-num-num-name)",
  "pattern_type": "mask",
  "pattern": "{prefix}-{num1}-{num2}-{name}",
  "priority": 1,
  "active": true,
  "allow_hyphen_variants": true,
  "example_samples": ["bl-13-9-flamingo", "inf-10-14-pawpatrol"]
}
```

---

## Linhas simples (b99, hallowen)

Itens como `b99` e `hallowen` **não** batem nos masks acima (não têm 4 ou 5 segmentos com hífens). O parser já trata isso com:

1. **Regex simples** embutido (`SKU_PATTERN_SIMPLE`: 2+ caracteres alfanuméricos)
2. **Fallback first_token**: se a linha não bater em nenhum layout/regex, o primeiro token da linha é usado como SKU (desde que não seja só número)

Por isso não é obrigatório ter um terceiro layout só para “um token”. Se quiser ser explícito, pode criar um layout **regex** com prioridade 2:

| Campo | Valor |
|-------|--------|
| **name** | `Picklist SKU simples (um token)` |
| **pattern_type** | `regex` |
| **pattern** | `\b[a-z0-9]{2,}\b` |
| **priority** | `2` |

Assim, linhas como `b99` ou `hallowen` batem nesse layout quando a linha inteira for só esse token.

---

## Resumo

| Prioridade | Layout | Exemplos de linha |
|------------|--------|-------------------|
| 0 | Mask 5 seg: `{prefix}-{num1}-{num2}-{name}-{size}` | s-6-3-wolf-g4, bl-7-4-butterfly-p, u-11-8-moonsun-p |
| 1 | Mask 4 seg: `{prefix}-{num1}-{num2}-{name}` | bl-13-9-flamingo |
| (opcional) 2 | Regex: `\b[a-z0-9]{2,}\b` | b99, hallowen |

O parser usa o **full_match** da linha, normaliza com `normalize_sku_from_pdf` (lowercase, sem separadores) e gera o mesmo `sku_normalized` que você usa no catálogo e no resolver (ex.: `s-6-3-wolf-g4` → `s63wolfg4`).
