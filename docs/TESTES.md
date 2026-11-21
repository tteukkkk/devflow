# Verificação da v1.0 — DevFlow

## Automação de backend

**Resultado local:** 19 testes aprovados via `python -m pytest -q`.

Cobertura:
- Cadastro/login/logout, validação de senha e cabeçalhos da API.
- Proteção CSRF e rejeição de estados e datas inválidos.
- Gestão de tarefas, versionamento de edição e rejeição de dados desatualizados.
- Etiquetas, comentários e checklists.
- Isolamento entre workspaces em leituras e gravações.
- Restrições de visualizadores e proteção do proprietário.
- Convites vinculados a e-mail e uso único.
- Bloqueio de responsáveis e etiquetas de outras equipes.
- Exportação CSV com neutralização de fórmulas.
- Verificação de notificações e números de tarefas por projeto.
- Projeto arquivado não recebe tarefas.
- Integração GitHub, importação sem duplicação e WebSocket.

## Interface

As capturas `previews/*.png` foram produzidas com templates HTML/CSS/JS reais, usando uma resposta previamente obtida da API autenticada local e renderização Chromium. O navegador de capturas deste ambiente possui bloqueio administrativo de navegação HTTP, portanto ele renderizou o frontend com respostas gravadas, sem navegar pela aplicação online. As ações de backend foram verificadas separadamente com TestClient.

Foram verificadas visualmente: landing, tela de login, painel, Kanban, detalhes da tarefa, relatórios, equipe, modos claro/escuro e viewport mobile. A rotina de prévia registrou **zero exceções JavaScript** e **nenhuma rolagem horizontal na raiz do documento** nas telas capturadas.

## Limites do escopo

Não foram realizados testes em produção, carga com vários processos, webhooks de terceiros, envio de e-mails ou sincronização bidirecional do GitHub. A versão entregue é uma base avançada demonstrável e não substitui homologação comercial.
