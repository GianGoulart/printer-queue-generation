### Prompt Template — Agente de IA para Desenvolvimento (por tarefa)

Use este template para executar **uma tarefa por vez** com rastreabilidade e critérios de aceite claros.

#### Contexto do produto
Você está desenvolvendo um serviço web multi-tenant (API + fila) para automação de bases DTF. O sistema recebe picklist PDF, extrai itens (Docling), resolve artes por SKU via Postgres + trigram, aplica regras de dimensionamento, executa encaixe (BEST_FIT ou PDF_ORDER), gera 1..N PDFs (Base 1, Base 2…), preview e manifesto. SKU não encontrado deve colocar job em `needs_input`.

#### Regras do MVP
- Output principal: PDF.
- SKU não encontrado: `needs_input`.
- Fonte de artes por tenant: configurável (Dropbox/S3/local), com driver comum.

---

## TEMPLATE (preencha os campos)

**Tarefa:** <título curto>

**Objetivo:**
- <o que será entregue>

**Escopo (incluir):**
- <itens que devem ser feitos>

**Fora de escopo (não fazer):**
- <itens que não devem ser feitos>

**Entradas:**
- <arquivos/configs/endpoints envolvidos>

**Saídas esperadas:**
- <arquivos/rotas/tabelas/funções>

**Critérios de aceite (testáveis):**
1. <critério 1>
2. <critério 2>
3. <critério 3>

**Considerações técnicas:**
- Linguagem: Python 3.11+
- API: FastAPI
- Fila: Redis + (Celery ou RQ)
- DB: Postgres + pg_trgm
- Parser: Docling
- Storage: S3/R2

**Plano de implementação (passo a passo):**
1. ...
2. ...

**Plano de testes:**
- Unit:
- Integração:
- Manual:

**Riscos e mitigação:**
- ...

**Entregáveis:**
- Lista final do que foi alterado/criado
- Como validar localmente

---

## EXEMPLO (Tarefa real)

**Tarefa:** Implementar busca de assets por SKU (exato + trigram)

**Objetivo:**
- Criar função `resolve_asset(tenant_id, sku)` que retorna o melhor asset ou `None`.

**Escopo (incluir):**
- Query exata por `tenant_id` + `sku_normalized`
- Fallback trigram com limiar e ordenação por `similarity`
- Caso ambíguo retorna `None` (força `needs_input`)

**Fora de escopo:**
- Upload de arte pelo endpoint resolve (pode ser V1.1)

**Critérios de aceite:**
1. Dado SKU exato existente, retorna o asset correto.
2. Dado SKU com variação pequena no filename, retorna asset via trigram com `score >= threshold`.
3. Dado dois candidatos muito próximos, retorna `None`.

**Plano de testes:**
- Criar fixtures com SKUs similares e validar comportamento.
