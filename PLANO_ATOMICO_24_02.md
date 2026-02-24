# Plano de Implementacao Atomico — OAZ StyleSheet PLM

> Projeto: OAZ StyleSheet PLM (FGcategoriaprodutooaz)
> Periodo: 23/02/2026 a 24/02/2026

---

- [x] Integração Fluxogama — Criar pacote `app/integrations/fluxogama/` com `__init__.py`, `field_map.json`, `mapper.py` e `client.py` [23/02/2026]
- [x] Integração Fluxogama — Criar blueprint `app/routes/fluxogama.py` com rotas de preview, envio unitario e envio em lote [23/02/2026]
- [x] Integração Fluxogama — Registrar `fluxogama_bp` em `app/routes/__init__.py` [23/02/2026]
- [x] Integração Fluxogama — Adicionar rota de envio em lote de Fichas Tecnicas (`POST /api/fluxogama/send-batch`) [23/02/2026]
- [x] Integração Fluxogama — Adicionar rota de envio em lote de Specifications/PDFs (`POST /api/fluxogama/send-batch-specs`) [23/02/2026]
- [x] Integração Fluxogama — Configurar variaveis `OAZ_BASE_URL`, `OAZ_CHAVE`, `OAZ_MODELO_PUSH_PATH` no `.env.local` [23/02/2026]
- [x] Integração OAZ — Criar pacote `app/integrations/oaz/` com `client.py`, `mapper.py` e `validator.py` [23/02/2026]
- [x] Integração OAZ — Implementar endpoints de health, mapping, preview e push em `app/routes/api.py` [23/02/2026]
- [x] Importação Banco OAZ — Criar `app/utils/banco_parser.py` para parsing de XLSX com auto-detecção de colunas (Codigo, WSID, Descricao, Status) [23/02/2026]
- [x] Importação Banco OAZ — Criar `app/routes/oaz_banco.py` com rotas de upload, preview, confirmação e status de importação [23/02/2026]
- [x] Importação Banco OAZ — Criar template `templates/oaz_banco_import.html` com UI completa (drag-drop, preview, progresso) [23/02/2026]
- [x] Importação Banco OAZ — Implementar auto-detecção de `field_key` (uno.10, uno.11, etc.) via aliases no nome do arquivo/aba [23/02/2026]
- [x] Importação Banco OAZ — Implementar processamento em background com thread, job tracking e polling de status [23/02/2026]
- [x] Importação Banco OAZ — Implementar batch upsert em `oaz_value_map` com controle de criados/atualizados/erros [23/02/2026]
- [x] Migração — Criar `migrate_dev.py` para migração de colunas no banco de desenvolvimento [23/02/2026]
- [x] Migração — Criar `migrate_fluxogama.py` e `migrate_oaz_columns.py` para colunas adicionais [23/02/2026]
- [x] Migração — Criar `migrate_source_name.py` para coluna `source_name` na tabela `oaz_value_map` [23/02/2026]
- [x] Verificação — Criar `check_fichas.py` para validar cobertura de campos uno e resolução De/Para (WSID) [23/02/2026]
- [x] Verificação — Criar `check_db.py` e `check_dev.py` para testes de conectividade com banco Neon [23/02/2026]
- [x] Fix — Corrigir conexão com banco de dados Neon (estava conectando local em vez do cloud) [23/02/2026]
- [x] Thumbnails — Gerar thumbnails para PDFs de especificações existentes (`static/thumbnails/`) [23/02/2026]
- [x] Uploads — Subir PDFs de especificações (`BLUSA_MAELE`, `BLUSA_MALHA`, `CALCA_MELANIE`, etc.) [23/02/2026]

---

- [ ] Integração Fluxogama — Testar preview via browser (`GET /api/fluxogama/payload/ficha/<id>/item/<id>`)
- [ ] Integração Fluxogama — Testar dry-run de envio (`POST /api/fluxogama/send/ficha/<id>/item/<id>?dry_run=1`)
- [ ] Integração Fluxogama — Testar envio real apos confirmar chave e endpoint com o Fluxogama
- [ ] Integração Fluxogama — Validar resposta de retorno do Fluxogama e tratar erros
- [ ] Integração OAZ — Testar endpoint `GET /api/oaz/health` para verificar conectividade com API OAZ
- [ ] Integração OAZ — Testar preview de payload OAZ (`GET /api/fichas/<id>/oaz/preview`)
- [ ] Integração OAZ — Testar push real para API OAZ com `dry_run=true` primeiro
- [ ] Importação Banco OAZ — Testar upload de multiplos arquivos XLSX simultaneamente
- [ ] Importação Banco OAZ — Verificar que override manual de `field_key` funciona no preview
- [ ] Importação Banco OAZ — Validar que registros inativos (Status != Ativo) sao ignorados corretamente
- [ ] Verificação — Executar `check_fichas.py` e confirmar cobertura de campos uno nos itens existentes
- [ ] Verificação — Confirmar que todos os valores De/Para (oaz_value_map) resolvem WSID corretamente
- [ ] Frontend — Adicionar botao "Enviar ao Fluxogama" na tela de edição do Item
- [ ] Frontend — Adicionar botao "Preview Fluxogama" com modal de JSON formatado
- [ ] Frontend — Implementar feedback visual de sucesso/erro apos envio para Fluxogama
- [ ] Frontend — Adicionar indicador de status de integracao na tabela de itens (icone/badge)
- [ ] Frontend — Adicionar botao de envio OAZ na interface do usuario (push para API OAZ)
- [ ] Configuração — Garantir que campo `colecao` esta incluido no XLSX de importacao de fichas
- [ ] Testes — Criar testes automatizados para `banco_parser.py` (variações de formato XLSX)
- [ ] Testes — Criar testes automatizados para `mapper.py` do Fluxogama (build payload)
- [ ] Testes — Criar testes automatizados para `mapper.py` do OAZ (build payload OAZ)
- [ ] Deploy — Atualizar `.env.prod` com variaveis de integracao OAZ/Fluxogama para producao
- [ ] Deploy — Executar migrations em ambiente de producao (Neon)
