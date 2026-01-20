### MVP Backlog — Serviço de Automação de Filas/Bases DTF (Picklist → PDF Print-Ready)

#### Visão
Construir um serviço web multi-tenant (API + fila) que recebe um picklist em PDF, extrai itens (SKU/quantidade/tamanho), resolve artes por SKU, aplica regras de dimensionamento, executa encaixe (modo sequência ou menos perda), e gera 1..N PDFs de base (Base 1, Base 2…) com preview e manifesto.

#### Decisões já fechadas
- **SKU não encontrado → job vira `needs_input` (MVP).**
- **Formato de output → PDF é suficiente (MVP).**
- Fonte de artes por tenant: **configurável** (Dropbox, bucket próprio, local), podendo **migrar para bucket nosso** por decisão do cliente.
- Indexação: **Postgres + `pg_trgm`** (match exato + fuzzy).
- Normalização do picklist PDF: **Docling**.

---

## Épico 0 — Fundamentos (multi-tenant, auth, modelo de dados)

### US-0.1 — Multi-tenant por `tenant_id`
**Como** plataforma
**Quero** garantir que todos os recursos (jobs, assets, outputs, configs) sejam escopados por `tenant_id`
**Para** evitar vazamento de dados entre empresas.

**Critérios de aceite**
- Toda tabela e endpoint relevante usa `tenant_id`.
- Consultas sempre filtram por `tenant_id`.
- Outputs em storage usam prefixo por tenant: `tenant/{tenant_id}/...`.

### US-0.2 — Autenticação e autorização (MVP)
**Como** usuário integrador
**Quero** autenticar via token
**Para** acessar apenas recursos do meu tenant.

**Critérios de aceite**
- Header `Authorization: Bearer <token>` obrigatório.
- Token mapeia para `tenant_id` (server-side).

### US-0.3 — Banco de dados inicial
**Como** desenvolvedor
**Quero** schema inicial em Postgres
**Para** suportar jobs, assets, configurações por tenant.

**Critérios de aceite**
- Extensão `pg_trgm` habilitada.
- Tabelas mínimas: `tenants`, `machines`, `tenant_storage_configs`, `assets`, `jobs`, `job_items`, `sizing_profiles`.

---

## Épico 1 — Configuração de origem de artes por tenant

### US-1.1 — Configurar storage do tenant
**Como** admin do tenant
**Quero** cadastrar onde estão minhas artes (provider + base_path + credenciais)
**Para** o sistema conseguir listar/baixar arquivos.

**Critérios de aceite**
- Suporta ao menos 2 providers no MVP: `s3_compatible` e `dropbox` (ou `local`, se necessário).
- Credenciais armazenadas de forma segura (MVP: no DB com criptografia; ideal: secret manager).

### US-1.2 — Driver de storage (download e listagem)
**Como** sistema
**Quero** uma interface comum para `list_files()` e `download(file_uri)`
**Para** trocar provider sem mudar o pipeline.

**Critérios de aceite**
- Implementação por provider com mesma assinatura.
- Timeouts e retries configuráveis.

---

## Épico 2 — Indexação e resolução de artes por SKU

### US-2.1 — Indexador de assets por tenant
**Como** sistema
**Quero** varrer a base de arquivos do tenant e criar/atualizar `assets`
**Para** resolver SKUs sem trabalho manual.

**Critérios de aceite**
- Job de reindexação (assíncrono) por tenant.
- Captura `original_filename`, `file_uri`, `updated_at` (quando disponível).
- Normalização do identificador: `sku_normalized` (lowercase, trims, etc.).

### US-2.2 — Busca por SKU (exata + trigram)
**Como** worker
**Quero** encontrar o melhor asset para um SKU lido do picklist
**Para** montar a base automaticamente.

**Critérios de aceite**
- Primeiro tenta match exato.
- Depois tenta fuzzy via trigram (`%` + `similarity`) com limiar configurável.
- Se ambíguo (score baixo ou múltiplos candidatos próximos), marca como `missing` (vai para `needs_input`).

---

## Épico 3 — Ingestão do picklist e normalização (Docling)

### US-3.1 — Upload do picklist e criação de job
**Como** usuário
**Quero** enviar um picklist (PDF) e parâmetros do job
**Para** iniciar o processamento.

**Critérios de aceite**
- `POST /v1/jobs` retorna `202` com `job_id`.
- PDF é armazenado em object storage.

### US-3.2 — Parser com Docling
**Como** worker
**Quero** converter o picklist PDF em estrutura de texto/JSON e extrair itens
**Para** obter `sku`, `quantity`, `size_label`.

**Critérios de aceite**
- Extrai itens com taxa de sucesso definida (ex.: >= 95% em PDFs-alvo).
- Armazena extração bruta (para auditoria).

---

## Épico 4 — Regras de dimensionamento e validações

### US-4.1 — Perfis de dimensionamento por tamanho
**Como** admin do tenant
**Quero** configurar regras do tipo `size_label -> target_width_mm`
**Para** padronizar a largura final da estampa.

**Critérios de aceite**
- API/CRUD simples (ou seed inicial no DB no MVP).
- Fallback default se não houver regra explícita.

### US-4.2 — Validação de DPI e formato
**Como** sistema
**Quero** bloquear artes com DPI baixo e formato incompatível
**Para** evitar impressão ruim.

**Critérios de aceite**
- DPI mínimo parametrizável por tenant/máquina.
- Bloqueia o job com erro claro ou marca itens como inválidos; no MVP, se qualquer item inválido, job vai para `failed` (recomendação) **ou** `needs_input` (se quiser correção manual). (Decidir durante implementação.)

### US-4.3 — Ajuste de escala para caber na largura útil
**Como** sistema
**Quero** reduzir escala proporcionalmente quando a dimensão final ultrapassar a largura útil
**Para** garantir que tudo imprima.

**Critérios de aceite**
- Registro de warning no manifesto (percentual de redução).

---

## Épico 5 — Motor de layout/encaixe (Packing)

### US-5.1 — Modo `PDF_ORDER` (sequência)
**Como** operador
**Quero** gerar base respeitando a ordem do PDF
**Para** facilitar conferência e separação.

**Critérios de aceite**
- Mantém ordem; se parametrizado, suporta `sequence_window` (lookahead N).

### US-5.2 — Modo `BEST_FIT` (menos perda)
**Como** gestor
**Quero** priorizar melhor encaixe e menor consumo de filme
**Para** reduzir custo.

**Critérios de aceite**
- Heurística determinística (ex.: sort por área/altura + best-fit).

### US-5.3 — Quebra automática em Base 1..N (limite 2,5m)
**Como** sistema
**Quero** criar automaticamente Base 2, Base 3… ao atingir o limite
**Para** não estourar a máquina.

**Critérios de aceite**
- Cada item recebe `base_index`, `x_mm`, `y_mm`.

### US-5.4 — Rotação 90° parametrizável
**Como** usuário
**Quero** habilitar/desabilitar rotação 90°
**Para** atender fluxos que proíbem rotação.

---

## Épico 6 — Render e outputs

### US-6.1 — Gerar PDF(s) de base
**Como** sistema
**Quero** renderizar 1..N PDFs print-ready
**Para** abrir no Corel/RIP.

**Critérios de aceite**
- PDFs são salvos no object storage.
- Tamanho do documento reflete mm reais (escala consistente).

### US-6.2 — Preview e manifesto
**Como** usuário
**Quero** preview e manifesto JSON
**Para** validar e auditar.

**Critérios de aceite**
- Preview por base.
- Manifesto inclui warnings (escala reduzida, etc.) e erros.

---

## Épico 7 — Estados de job e `needs_input`

### US-7.1 — Job `needs_input` para SKU não encontrado
**Como** usuário
**Quero** ver quais SKUs faltaram e resolver
**Para** retomar o processamento.

**Critérios de aceite**
- Se 1+ SKUs não resolvidos, job termina etapa de parsing/resolução e entra em `needs_input`.
- Endpoint de resolução permite apontar `asset_id` correto (ou upload em V1.1).

---

## Épico 8 — Observabilidade e operação

### US-8.1 — Logs e rastreabilidade por job
**Como** operador do sistema
**Quero** logs estruturados e métricas
**Para** depurar falhas e medir performance.

**Critérios de aceite**
- Logs com `job_id`, `tenant_id`.
- Métricas: tempo por etapa, taxa de `needs_input`, taxa de falhas.
