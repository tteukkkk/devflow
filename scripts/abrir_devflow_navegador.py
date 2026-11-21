"""Abre o DevFlow quando o servidor disponibiliza a página de autenticação.

A rota pública de login é /entrar. /login é apenas um alias de compatibilidade.
"""
import time
import urllib.error
import urllib.request
import webbrowser

LOGIN_URL = 'http://127.0.0.1:8010/entrar'

for _ in range(60):
    try:
        with urllib.request.urlopen(LOGIN_URL, timeout=1.5) as response:
            page = response.read(5000).decode('utf-8', errors='ignore').lower()
            if response.status == 200 and 'devflow' in page and '<form' in page:
                webbrowser.open(LOGIN_URL, new=2)
                break
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(0.5)
else:
    print(f'Não foi possível abrir automaticamente. Acesse: {LOGIN_URL}')
