# 🗂️ Plano de Implementação — Integração Fluxogama

> **Projeto:** OAZ StyleSheet PLM  
> **Data:** 09/02/2026  

---

## Tarefas Realizadas Hoje

### 🔍 Análise

- [x] Verificar estrutura de `FichaTecnicaItem` e `FichaTecnica` para confirmar campos disponíveis
- [x] Validar que `raw_row` (JSON) está sendo salvo pelo `excel_parser.py` para campos não mapeados
- [x] Confirmar uno.X corretos com o modelo do Fluxogama:
  - Fornecedor → `uno.8` | Origem → `uno.9` | Incoterm → `uno.21`
  - Canal → `uno.74` | NCM → `uno.50` | Status → `uno.7`
  - Material Principal → `uno.24` | Desc. Site → `uno.386` | Obs. → `uno.443`

### ⚙️ Backend

- [x] Criar pacote `app/integrations/fluxogama/` (`__init__.py`)
- [x] Criar `field_map.json` — mapeamento configurável (25 campos uno + 4 top-level, com `type: db`, `max_len`, `template`, `computed`)
- [x] Criar `mapper.py` — construtor de payload (resolução: model → header → raw_row → default, normalização de datas, validação obrigatórios, truncamento)
- [x] Criar `client.py` — cliente HTTP via `urllib` com dry-run, timeout 30s, tratamento de erros HTTP
- [x] Criar `app/routes/fluxogama.py` — blueprint com `GET preview` + `POST send` (CSRF exempt, controle de acesso, bloqueio 422 se erros)
- [x] Registrar `fluxogama_bp` em `app/routes/__init__.py`

### 🔧 Configuração

- [x] Adicionar variáveis no `.env.local`: `FLUXOGAMA_BASE_URL`, `FLUXOGAMA_CHAVE`, `FLUXOGAMA_ENDPOINT_ENVIO`
- [ ] Substituir placeholder `FLUXOGAMA_CHAVE` pela chave real
- [ ] Confirmar rota exata do endpoint de envio com o Fluxogama

### 🖥️ Frontend (Pendente)

- [ ] Adicionar botão "Enviar ao Fluxogama" na tela de edição do Item
- [ ] Adicionar botão "Preview Fluxogama" com modal de JSON formatado
- [ ] Implementar feedback visual de sucesso/erro após envio
- [ ] Indicador de status de integração na tabela de itens
- [ ] Botão de envio em lote (múltiplos itens)

### ✅ Verificação

- [x] Importar `mapper.py` e `client.py` sem erros
- [x] Carregar `field_map.json` — 25 campos uno + 4 top-level
- [x] Gerar payload com dados reais (ficha:7, item:4) — 29 campos, NCM=`6911.10.10`, Incoterm=`FOB`
- [x] Servidor Flask reiniciou sem erros com blueprint registrado
- [ ] Testar preview via browser (`GET /api/fluxogama/payload/ficha/7/item/4`)
- [ ] Testar dry-run (`POST ...?dry_run=1`)
- [ ] Testar envio real após configurar chave
- [ ] Validar resposta do Fluxogama

---

## Arquivos Criados/Modificados Hoje

| Ação | Arquivo |
|------|---------|
| NEW | `app/integrations/__init__.py` |
| NEW | `app/integrations/fluxogama/__init__.py` |
| NEW | `app/integrations/fluxogama/field_map.json` |
| NEW | `app/integrations/fluxogama/mapper.py` |
| NEW | `app/integrations/fluxogama/client.py` |
| NEW | `app/routes/fluxogama.py` |
| MOD | `app/routes/__init__.py` |
| MOD | `.env.local` |

---

## Pendências Críticas

| Prioridade | Pendência |
|------------|-----------|
| 🔴 Alta | Configurar `FLUXOGAMA_CHAVE` real no `.env.local` |
| 🔴 Alta | Confirmar endpoint exato de envio com o Fluxogama |
| 🟡 Média | Garantir campo `colecao` no XLSX de importação |
| 🟡 Média | Implementar botões de frontend (preview + envio) |
| 🟢 Baixa | Envio em lote + testes automatizados |
