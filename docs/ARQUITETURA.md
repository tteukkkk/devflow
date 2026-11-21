# Arquitetura do DevFlow

## Camadas

- **Frontend:** HTML + CSS + JavaScript sem framework obrigatório. API JSON com `fetch`, autenticação por cookie, WebSocket para notificações sobre alterações, interface SPA servida em `/app`.
- **Backend:** Python + FastAPI + Pydantic para validação, handlers e regras de autorização.
- **Persistência:** SQLAlchemy 2.x, esquema normalizado, SQLite no desenvolvimento. PostgreSQL previsto para produção.
- **Sessão e segurança:** cookie assinado HttpOnly, SameSite Lax, modo HTTPS configurável, token CSRF por sessão em header para comandos JSON, Argon2.

## Modelo relacional

`User` possui memberships em um ou mais `Workspace`. Cada workspace possui vários `Project`, `Label`, `Activity`, `Notification` e `Invitation`. Cada projeto possui `Task` com identificador sequencial. Tarefas possuem comentários, itens de checklist e etiquetas N:N. `GitHubIntegration` vincula um repositório a um projeto, e `ImportedGitHubIssue` evita duplicação de importações de issues.

## Isolamento entre empresas

Toda rota de recurso recebe `workspace_id` e valida a associação do usuário autenticado antes de consultar projeto, tarefa ou informações da equipe. IDs de entidades são validados em conjunto com o workspace; não é suficiente conhecer um ID global.

## Segurança de escrita

Todas as operações de modificação autenticadas exigem `X-CSRF-Token`. Os usuários com perfil **viewer** acessam somente leitura. As versões numéricas de tarefa permitem rejeitar uma atualização desatualizada com HTTP 409. Para vários processos e PostgreSQL sob carga, reforçar a atualização de versão em uma única instrução transacional com bloqueios ou compare-and-swap no banco.

## Sincronização colaborativa

`/ws/{workspace_id}` valida a sessão e a participação no workspace. Os clientes recebem eventos sobre criação/edição de tarefas e comentários. O navegador busca novamente os dados autenticados. **Limitação:** o hub WebSocket é armazenado no processo. Em ambiente com múltiplas réplicas, usar Redis Pub/Sub, sistema de filas ou similar.

## GitHub

Cada projeto pode associar `usuario/repositorio`. A API consulta apenas o host oficial `api.github.com` e limita a lista às issues abertas; solicitações de pull request são filtradas. A importação cria uma tarefa com referência de origem e grava um vínculo único para evitar duplicação. Opcionalmente, `DEVFLOW_GITHUB_TOKEN` aumenta os limites de consulta conforme permissões da conta. Não existe sincronização automática de status, comentários ou estados.

## Rotas de destaque

- `POST /api/auth/register` / `POST /api/auth/login` / `POST /api/auth/logout`
- `GET /api/bootstrap`
- `GET /api/workspaces/{wid}/data`
- `POST/PATCH /api/workspaces/{wid}/projects...`
- `POST/PATCH/GET /api/workspaces/{wid}/tasks...`
- `POST .../tasks/{tid}/comments`
- `POST/PATCH/DELETE .../tasks/{tid}/checklist...`
- `POST .../invites` e `POST /api/invites/{token}/accept`
- `PUT .../projects/{pid}/github`, `GET .../github/issues`, `POST .../github/issues/{number}/import`
- `GET /api/workspaces/{wid}/export.csv`
- `WS /ws/{wid}` e `GET /api/health`
