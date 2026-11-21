# Checklist antes de disponibilizar o DevFlow para clientes

A aplicação é adequada para demonstração e avaliação técnica. **A versão atual ainda não foi homologada para operação comercial.**

## Obrigatório antes de dados e clientes reais

1. Criar infraestrutura de hosting com domínio e HTTPS obrigatório (reverse proxy), HSTS, cookies seguros e segredos externos ao repositório.
2. Migrar para PostgreSQL e implementar migrações versionadas Alembic, inclusive atualização de dados e rollback testado.
3. Validar concorrência de tarefas e importações em múltiplas réplicas; usar atualização transacional atômica de sequência e `version`.
4. Implementar rate limiting compartilhado com Redis, proteção contra força bruta e instrumentação de tentativas malsucedidas. O rate limiter atual é apenas por processo.
5. Contratar, configurar e testar e-mails transacionais para entrega de convites, redefinição de senha, notificações e relatórios de entregabilidade.
6. Criar autenticação adicional (MFA para administradores), troca e recuperação de senha, gerenciamento/revogação de sessões e retenção segura de logs.
7. Configurar métricas, logs estruturados, alertas, rastreamento de exceções e testes de disponibilidade.
8. Backups criptografados, restauração ensaiada, regras de retenção e plano de resposta a incidentes.
9. Política de privacidade, termos, direitos dos titulares, contratos com operadores e avaliação LGPD para o mercado pretendido.
10. Executar testes de carga, varredura de dependências, validação de XSS/CSRF, revisão de permissões e auditoria independente.
11. Migrar o serviço de eventos WebSocket para solução distribuída e escalável (Redis Pub/Sub ou equivalente).
12. Configurar cabeçalhos CSP adequados a scripts externos, fontes e integrações; revisar dependências externas e aplicar SRI onde aplicável.

## Extras comerciais para uma segunda versão

- Sprints, marcos e automações de fluxo de trabalho.
- Anexos com armazenamento em objeto, antivírus, limites de tamanho e URLs temporárias.
- Gestão de organizações, faturamento/assinaturas e limites por plano.
- Integrações bidirecionais com GitHub e provedores de identidade.
- Exportação integral e importação de projetos, trilha de auditoria detalhada e lixeira com retenção.
- Acessibilidade verificada com usuários, testes E2E em navegadores reais e testes mobile por toque.

Não publicar dados de demonstração nem senhas exemplificativas no ambiente de produção. O checkout e o faturamento **não** fazem parte do DevFlow nesta versão; não anunciar planos pagos até implementar e validar a cobrança.
