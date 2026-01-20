# PDF Parsing Order Behavior

## 📋 Como a Ordem dos SKUs é Determinada

### 🎯 **Ordem do PDF Original (Preservada)**

O sistema **preserva a ordem exata** em que os SKUs aparecem no PDF:

- ✅ **Fidelidade**: Mesma ordem visual do picklist original
- ✅ **Página-por-Página**: Processa página 1, depois 2, depois 3...
- ✅ **Top-to-Bottom, Left-to-Right**: Dentro de cada página, segue ordem de leitura natural
- ✅ **Reprodutibilidade**: Múltiplas execuções geram resultado idêntico

### 📄 **Fluxo de Processamento**

```
1. PDF Upload → 2. Parser Extrai SKUs (página 1 → 2 → 3...) → 3. Atribuir Posições (ordem do PDF)
```

**Exemplo:**

```
PDF Página 1:
  Linha 1: bl-11-8-moonsun-p
  Linha 2: bl-13-9-flamingo-m
  Linha 3: bl-5-2-blackcat-m

PDF Página 2:
  Linha 1: inf-1-6-unicorn-4
  Linha 2: inf-10-14-pawpatrol-2

Ordem Final (preserva ordem do PDF):
1. bl-11-8-moonsun-p      → position=1 (Página 1, Linha 1)
2. bl-13-9-flamingo-m     → position=2 (Página 1, Linha 2)
3. bl-5-2-blackcat-m      → position=3 (Página 1, Linha 3)
4. inf-1-6-unicorn-4      → position=4 (Página 2, Linha 1)
5. inf-10-14-pawpatrol-2  → position=5 (Página 2, Linha 2)
```

---

## 🔧 **Modos de Packing**

### **Mode: `sequence`**

Mantém a **ordem exata do PDF** no layout final:

```json
{
  "mode": "sequence",
  "packing": {
    "bases": [{
      "placements": [
        {"sku": "bl-11-8-moonsun-p", "x_mm": 20, "y_mm": 20},       ← 1º no PDF
        {"sku": "bl-13-9-flamingo-m", "x_mm": 90, "y_mm": 20},      ← 2º no PDF
        {"sku": "bl-5-2-blackcat-m", "x_mm": 160, "y_mm": 20}       ← 3º no PDF
      ]
    }]
  }
}
```

### **Mode: `optimize`**

Reordena por **área (maior → menor)** para otimizar espaço:

```json
{
  "mode": "optimize",
  "packing": {
    "bases": [{
      "placements": [
        {"sku": "plus-12-7-panda-g3", "width_mm": 120},    ← Maior
        {"sku": "u-18-13-metallica", "width_mm": 90},
        {"sku": "bl-9-7-mermaid", "width_mm": 70}          ← Menor
      ]
    }]
  }
}
```

---

## 🚀 **Ordem Personalizada (Futuro)**

Para fornecer uma ordem específica do picklist original, você pode:

### **Opção A: Via API**

```bash
curl -X POST "http://localhost:8000/v1/jobs" \
  -H "X-Tenant-ID: 1" \
  -F "file=@picklist.pdf" \
  -F "mode=sequence" \
  -F "machine_id=1" \
  -F "custom_order=[\"sku1\", \"sku2\", \"sku3\"]"  # ← Ordem desejada
```

### **Opção B: Picklist Estruturado (JSON)**

```bash
curl -X POST "http://localhost:8000/v1/jobs/from-json" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": 1,
    "mode": "sequence",
    "items": [
      {"sku": "bl-9-7-mermaid", "quantity": 1},
      {"sku": "inf-2-8-spider6", "quantity": 2},
      {"sku": "u-18-13-metallica", "quantity": 1}
    ]
  }'
```

---

## 🔧 **Como o Sistema Garante Ordem Correta do PDF**

O parser usa **coordenadas de página + Y/X** para reconstruir a ordem exata:

### **Estratégia de Parsing:**

1. **Por Página**: Processa página 1 → 2 → 3... (ordem sequencial)
2. **Por Linha**: Agrupa palavras com Y similar (±2px de tolerância)
3. **Por Coluna**: Ordena palavras dentro da linha por X (esquerda → direita)
4. **Por Posição**: Atribui `position = 1, 2, 3...` na ordem de descoberta

### **Desafios Tratados:**

- ✅ **Múltiplas páginas**: Preserva ordem página-por-página
- ✅ **Múltiplas colunas**: Ordena left-to-right dentro de cada linha
- ✅ **Layouts complexos**: Usa coordenadas Y para definir "acima/abaixo"
- ⚠️ **Headers/footers**: Podem aparecer entre itens (limitação do PDF)

---

## ✅ **Garantias do Sistema**

| Aspecto | Comportamento |
|---------|---------------|
| **Parsing** | Extrai SKUs do PDF |
| **Ordenação** | Alfabética por SKU |
| **`picklist_position`** | 1, 2, 3... (ordem alfabética) |
| **`mode=sequence`** | Respeita `picklist_position` |
| **`mode=optimize`** | Ignora `picklist_position`, reordena por área |
| **Consistência** | ✅ Múltiplas execuções = mesmo resultado |

---

## 📞 **Suporte**

Se você precisa de uma ordem específica diferente da alfabética, entre em contato para discutir soluções personalizadas.
