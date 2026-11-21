"""Configuração local idempotente: preserva usuários, banco e configurações existentes."""
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parent.parent
settings = root / '.env'
if not settings.exists():
    content = (
        'DEVFLOW_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n'
        'DEVFLOW_DATABASE_URL=sqlite:///./devflow.sqlite3\n'
        'DEVFLOW_BASE_URL=http://127.0.0.1:8010\n'
        'DEVFLOW_SECURE_COOKIES=0\n'
        'DEVFLOW_ENABLE_API_DOCS=0\n'
    )
    settings.write_text(content, encoding='utf-8')
    print('Configuração .env criada com chave aleatória local.')
else:
    print('Configuração .env existente preservada.')

if not (root / 'devflow.sqlite3').exists():
    import subprocess
    print('Criando conta e projetos de demonstração...')
    result = subprocess.run([sys.executable, str(root / 'scripts' / 'seed_demo.py')], cwd=root)
    if result.returncode:
        sys.exit(result.returncode)
else:
    print('Banco de dados existente preservado (sem resetar senhas ou usuários).')
