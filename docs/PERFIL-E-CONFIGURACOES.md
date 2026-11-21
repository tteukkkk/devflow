# DevFlow — Perfil, segurança e configurações (v1.1)

## Como usar

1. Abra `http://127.0.0.1:8010/app`, entre na conta e clique em **Configurações** na barra lateral.
2. Na seção **Meu perfil**, altere nome, e-mail de acesso e cor do avatar. Para salvar, digite a senha atual. Os dados são salvos no banco e aparecem para os integrantes dos workspaces dos quais você participa.
3. Em **Senha e segurança**, informe a senha atual, defina outra com pelo menos 10 caracteres (incluindo letras e números) e confirme.
4. Em **Workspace e aparência**, os administradores podem alterar o nome/descrição da equipe; qualquer integrante pode trocar o tema no navegador e exportar tarefas em CSV, desde que tenha acesso ao workspace.
5. O menu da conta, na parte inferior da lateral, dá acesso a **Meu perfil e segurança** e **Configurações**. O botão **Sair da conta** permanece separado e disponível.

## Segurança e limites

- As alterações de perfil e senha exigem autenticação e token CSRF. A senha atual precisa ser confirmada pelo próprio usuário. A aplicação aplica checagem de unicidade de e-mail e validação de cor hexadecimal.
- Senhas são armazenadas apenas por hash Argon2, nunca em texto puro; o app não fornece recuperação de senha por e-mail.
- Alterar a senha **não revoga automaticamente sessões existentes em outros navegadores** nesta versão. Para produção, implemente versionamento/revogação de sessões em servidor, autenticação robusta e fluxo de recuperação de conta.
- Troca de tema é uma preferência local do navegador; dados de perfil e workspace são persistidos no banco.
- O pacote demonstrativo inclui contas fictícias. Não use informações reais ou senhas pessoais na demonstração pública.

## Aplicando sobre uma instalação existente

Feche a aplicação. Extraia o patch na pasta que contém `KIT-3-PROJETOS` e confirme a substituição de **apenas** `DevFlow/devflow/app.py`, `DevFlow/templates/app.html`, `DevFlow/static/app.js`, `DevFlow/static/style.css` e arquivos auxiliares incluídos. Seu arquivo `.env` e banco SQLite existentes não são alterados.

Execute o mesmo `ABRIR_PROJETOS.bat` e abra o DevFlow. Se a interface antiga continuar em cache, pressione `Ctrl + F5`.
