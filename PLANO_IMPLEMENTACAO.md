# Plano de Implementação Atômico — Integração Fluxogama

**Projeto:** OAZ StyleSheet PLM — Módulo Fluxogama  
**Data:** 25/02/2026  
**Autor:** Arquiteto de Software / Tech Lead

---

## Commits realizados hoje

- [x] **Feature:** Implementar integração Fluxogama com field mapping, client HTTP, rotas de preview/envio, validação de payload, dedup, e frontend MVP (badges, modal batch, painel de item) [25/02/2026]
- [x] **Feature:** Armazenar claims JWT decodificados em variável dedicada para diagnóstico de 401/403, adicionar campo `audience` no check, atualizar gerador de bundle [25/02/2026]

## Alterações não commitadas (em andamento)

- [x] **Backend:** Adicionar logging estruturado de produção em `client.py` — URL, payload_size, ws_id, status, elapsed, error body (sem expor token) [25/02/2026]
- [x] **Backend:** Corrigir `fluxogama_sent_at` — agora só é preenchido quando `status == 'sent'`, não em caso de erro (evita confusão no frontend) [25/02/2026]
- [x] **Backend:** Adicionar campo `codigo` = `ws_id` no payload (`mapper.py`) para lookup estável no Fluxogama por identificador externo [25/02/2026]
- [x] **Backend:** Adicionar `import os` em `fluxogama.py` para leitura de variáveis de ambiente [25/02/2026]
- [x] **Backend:** Implementar suporte a `allow_create=1` na rota single-item (`/send/ficha/<id>/item/<id>`) — injeta `sistema_criar_modelo=1` + `subetapa` no payload [25/02/2026]
- [x] **Backend:** Implementar suporte a `allow_create=1` na rota batch (`/send-batch`) — resolve `subetapa` uma vez fora do loop, injeta em cada item [25/02/2026]
- [x] **Backend:** Guard 422 quando `subetapa` não está configurada (nem no env `FLUXOGAMA_SUBETAPA_WSID` nem no query param `?subetapa=<wsid>`) [25/02/2026]
- [x] **Verificação:** Restaurar variável `FLUXOGAMA_ENDPOINT_ENVIO=/rest/api/v1/remessa/modelo` no `.env.local` (removida acidentalmente ao atualizar token) [25/02/2026]
- [x] **Verificação:** Probe da API Fluxogama — descoberta de que POST espera array, necessita `sistema_criar_modelo=1` e `subetapa` para criação [25/02/2026]
- [x] **Verificação:** Teste real com token renovado — JWT válido (sem 401), endpoint correto (sem 404), 400 por falta de `sistema_criar_modelo` (esperado antes do patch) [25/02/2026]

## Pendências para conclusão (bloqueadas)

- [ ] **Configuração:** Obter o wsid da subetapa destino no Fluxogama e configurar `FLUXOGAMA_SUBETAPA_WSID` no `.env.local` [25/02/2026]
- [ ] **Verificação:** Resetar item 8 no banco (`fluxogama_status=NULL, sent_at=NULL, response=NULL`) [25/02/2026]
- [ ] **Verificação:** Reiniciar servidor (`python run.py`) para carregar novas env vars [25/02/2026]
- [ ] **Verificação:** Executar `python test_real_send.py` com `subetapa` configurada — esperado: 200 do Fluxogama com modelo criado [25/02/2026]
- [ ] **Verificação:** Confirmar dedup pós-envio — repetir POST sem `force`, esperado 409 [25/02/2026]
- [ ] **Verificação:** Confirmar force resend — POST com `?force=1`, esperado 200 [25/02/2026]
- [ ] **Frontend:** Verificar no browser que badge mudou para "Integrado" e `sent_at` está preenchido corretamente [25/02/2026]
- [ ] **Limpeza:** Remover scripts de teste temporários (`probe_fluxogama.py`, `test_sentat_fix.py`, `probe_output.txt`, `test_output.txt`) [25/02/2026]
- [ ] **Git:** Commitar todas as alterações pendentes com mensagem descritiva [25/02/2026]

## Arquivos modificados hoje (resumo)

| Arquivo | Tipo de alteração |
|---------|-------------------|
| `app/integrations/fluxogama/client.py` | Logging de produção (URL, elapsed, error body) |
| `app/integrations/fluxogama/mapper.py` | Campo `codigo` = ws_id, `_is_empty()` helper |
| `app/routes/fluxogama.py` | `allow_create`, `sistema_criar_modelo`, `subetapa`, `sent_at` fix, `import os` |
| `app/routes/api.py` | Retornar `fluxogama_status` e `fluxogama_sent_at` na API de itens |
| `templates/ficha_tecnica_item_edit.html` | Painel Fluxogama (Preview, Send, badges) |
| `templates/ficha_tecnica_table.html` | Coluna "Flux" com badges de status |
| `.env.local` | Token JWT renovado, `FLUXOGAMA_ENDPOINT_ENVIO` restaurado |
| `test_real_send.py` | Script de teste E2E (5 passos: preview → dry-run → real → dedup → force) |
| `test_dedup_dryrun.py` | Testes de dedup em dry-run (6/6 passed) |

## Bloqueador único

> **FLUXOGAMA_SUBETAPA_WSID** — sem o wsid da subetapa destino, o envio real retorna 422.  
> Este valor deve ser obtido com o time/portal do Fluxogama e configurado no `.env.local`.
