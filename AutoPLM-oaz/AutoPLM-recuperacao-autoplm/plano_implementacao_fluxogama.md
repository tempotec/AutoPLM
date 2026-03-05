# Plano de Implementação — OAZ AutoPLM × Fluxogama API [05/03/2026]

## Contexto

Integração do sistema OAZ AutoPLM com a API do Fluxogama para atualização automática de modelos (fichas técnicas). Até hoje, o sistema apenas **criava** modelos no Fluxogama (`sistema_criar_modelo=1`). O objetivo é implementar o fluxo completo: consultar IDs existentes via `/retorno/modelo` e atualizar modelos via `/remessa/modelo` usando o `id` do Fluxogama.

## Progresso — Tarefas Concluídas Hoje

- [x] **Análise**: Testar autenticação na API OAZ (`/autenticacao`) — Token JWT funcional com `Matheus.Parra` [05/03/2026]
- [x] **Análise**: Testar envio via `/remessa/modelo` — Identificar formato correto de payload para update [05/03/2026]
- [x] **Análise**: Mapear diferenças entre payload de criação (`sistema_criar_modelo=1`) vs atualização (`id: 11788`) [05/03/2026]
- [x] **Análise**: Descobrir formato correto do `/retorno/modelo` — `campos.campos` (plural) + `campo/operador/valor` [05/03/2026]
- [x] **Análise**: Testar permissões de contas — `Matheus.Parra` (API) vs `Integracao.Oaz` (UI apenas) [05/03/2026]
- [x] **Backend**: Adicionar campo `fluxogama_model_id` (Integer) ao model `Specification` em `app/models/specification.py` [05/03/2026]
- [x] **Backend**: Modificar `send_batch_specs` em `app/routes/fluxogama.py` — lógica UPDATE (via `id`) vs CREATE (via `sistema_criar_modelo`) [05/03/2026]
- [x] **Backend**: Executar migração DB — Coluna `fluxogama_model_id` adicionada + ID 11788 vinculado à spec S27TH033 [05/03/2026]
- [x] **Verificação**: Testar update manual via sistema — Spec S27TH033 (ID 11788) atualizada com sucesso (HTTP 200, "Atualizados 1/1") [05/03/2026]
- [x] **Verificação**: Testar `/retorno/modelo` com formato correto — Retorno OK com dados de modelos (paginação funcional) [05/03/2026]
- [x] **Frontend**: Adicionar botão "Selecionar todas" na página de Fichas Técnicas em `templates/fichas_list.html` [05/03/2026]

## Próximas Tarefas — Pendentes

- [ ] **Backend**: Criar módulo `app/integrations/fluxogama/retorno.py` — Função `buscar_modelo_por_referencia(referencia)` que consulta `/retorno/modelo` e retorna o `modelo.id`
- [ ] **Backend**: Adicionar nova etapa no pipeline de processamento (`batch_processor.py`) — Stage 6 `fluxogama_link` entre `supplier_link` e `completed` (Stage 7)
- [ ] **Backend**: Implementar `process_stage_fluxogama_link(spec, file_path, thread_session)` — Buscar ID do Fluxogama pelo `ref_souq` da spec durante o processamento
- [ ] **Backend**: Atualizar constantes de stages — `STAGE_FLUXOGAMA_LINK = 6`, `STAGE_COMPLETED = 7`
- [ ] **Backend**: Garantir que falha na busca do Fluxogama **não bloqueia** o processamento (log warning, continua)
- [ ] **Verificação**: Testar processamento de nova spec completa — Verificar que `fluxogama_model_id` é preenchido automaticamente na Stage 6
- [ ] **Verificação**: Testar spec sem match no Fluxogama — Confirmar que o processamento completa normalmente sem erro
- [ ] **Limpeza**: Remover arquivos de teste temporários da raiz (`test_*.json`, `test_oaz_api.py`, `add_fluxogama_model_id.py`)

## Referência Técnica — Formatos de API Descobertos

**Retorno (consulta):**
```json
POST /retorno/modelo
{
  "pagina": 1,
  "campos": { "campos": ["modelo.id", "modelo.ds_referencia", "modelo.ws_id"] },
  "filtros": [{"campo": "modelo.ds_referencia", "operador": "%like%", "valor": "S27TH033"}]
}
```

**Remessa (atualização):**
```json
POST /remessa/modelo
[{"id": 11788, "uno.38": "novo valor", "ws_id": "spec_632"}]
```

## Arquivos Modificados Hoje

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `app/models/specification.py` | MODIFY | Campo `fluxogama_model_id` adicionado |
| `app/routes/fluxogama.py` | MODIFY | Lógica UPDATE vs CREATE no `send_batch_specs` |
| `templates/fichas_list.html` | MODIFY | Botão "Selecionar todas" adicionado |
| `add_fluxogama_model_id.py` | NEW | Script de migração DB (pode ser removido) |

## Arquivos a Criar

| Arquivo | Descrição |
|---------|-----------|
| `app/integrations/fluxogama/retorno.py` | Função de consulta ao `/retorno/modelo` |
| `app/utils/batch_processor.py` | Modificar — Nova Stage 6 `fluxogama_link` |
