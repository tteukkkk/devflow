@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title DevFlow - inicializador Windows

echo.
echo ===================================================
echo    DEVFLOW 1.1.2 - Iniciador para Windows
echo ===================================================
echo.

if not exist "manage.py" (
  echo ERRO: arquivo manage.py nao encontrado.
  echo Extraia a pasta DevFlow inteira antes de executar este arquivo.
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Preparando ambiente Python...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      py -3.12 -m venv ".venv"
    ) else (
      py -3 -m venv ".venv"
    )
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERRO: Python nao encontrado. Instale Python 3.12 ou superior.
      echo Apos instalar, execute este arquivo novamente.
      goto :fail
    )
    python -m venv ".venv"
  )
  if errorlevel 1 goto :fail
)

".venv\Scripts\python.exe" -c "import sys;sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERRO: o ambiente precisa de Python 3.12 ou superior.
  echo Apague somente a pasta .venv e instale a versao correta do Python.
  goto :fail
)

echo [2/4] Verificando e instalando dependencias...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo ERRO: nao foi possivel instalar as dependencias.
  echo Verifique a conexao com a internet.
  goto :fail
)

echo [3/4] Preparando configuracoes locais...
".venv\Scripts\python.exe" scripts\preparar_devflow_local.py
if errorlevel 1 goto :fail

echo [4/4] Abrindo o DevFlow...
echo.
echo Acesse: http://127.0.0.1:8010/entrar
echo.
echo Se o navegador nao abrir sozinho, cole este endereco no navegador.
start "" /B ".venv\Scripts\python.exe" scripts\abrir_devflow_navegador.py
".venv\Scripts\python.exe" manage.py
if errorlevel 1 (
  echo.
  echo ERRO: O servidor parou. Verifique se a porta 8010 ja esta em uso.
  goto :fail
)
goto :end

:fail
echo.
echo A inicializacao nao foi concluida. Leia as mensagens acima.
pause
:end
endlocal
