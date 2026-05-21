@echo off
chcp 65001 >nul
title Installation — Système d'Archivage Intelligent NouvelAir

echo.
echo ============================================================
echo   Système d'Archivage Intelligent — NouvelAir MRO
echo   Script d'installation automatique Windows
echo ============================================================
echo.

REM ── Vérification Python ─────────────────────────────────────
echo [1/7] Vérification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python n'est pas installé ou pas dans le PATH.
    echo Téléchargez Python 3.11 sur https://python.org/downloads
    echo IMPORTANT : Cochez "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)
python --version
echo OK

REM ── Vérification PostgreSQL ──────────────────────────────────
echo.
echo [2/7] Vérification de PostgreSQL...
"C:\Program Files\PostgreSQL\15\bin\psql.exe" --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : PostgreSQL 15 n'est pas installé.
    echo Téléchargez PostgreSQL 15 sur https://postgresql.org/download/windows
    echo Utilisez le port 5434 lors de l'installation.
    pause
    exit /b 1
)
echo OK

REM ── Environnement virtuel ────────────────────────────────────
echo.
echo [3/7] Création de l'environnement virtuel Python...
if exist venv (
    echo Environnement virtuel déjà existant — ignoré.
) else (
    python -m venv venv
    echo OK
)

REM ── Activation venv ──────────────────────────────────────────
echo.
echo [4/7] Activation de l'environnement virtuel...
call venv\Scripts\activate.bat
echo OK

REM ── Installation des dépendances ────────────────────────────
echo.
echo [5/7] Installation des dépendances Python...
echo Cela peut prendre 5-10 minutes selon votre connexion internet.
echo.
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERREUR lors de l'installation des dépendances.
    pause
    exit /b 1
)
echo OK

REM ── Configuration .env ──────────────────────────────────────
echo.
echo [6/7] Configuration de l'environnement...
if not exist .env (
    if exist .env.example (
        copy .env.example .env
        echo Fichier .env créé depuis .env.example
        echo.
        echo IMPORTANT : Editez le fichier .env avec vos paramètres :
        echo   - DATABASE_URL : mot de passe PostgreSQL
        echo   - ARCHIVE_ROOT_PATH : chemin vers vos archives
        echo   - GROQ_API_KEY : clé API Groq
        echo.
        notepad .env
    ) else (
        echo ATTENTION : .env.example introuvable.
        echo Créez manuellement le fichier .env.
    )
) else (
    echo Fichier .env déjà existant — ignoré.
)

REM ── Création base de données ─────────────────────────────────
echo.
echo [7/7] Création de la base de données nouv_db...
set PGPASSWORD=postgres
"C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -p 5434 -c "SELECT 1 FROM pg_database WHERE datname='nouv_db'" | findstr "1 row" >nul 2>&1
if errorlevel 1 (
    "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -p 5434 -c "CREATE DATABASE nouv_db;"
    echo Base de données nouv_db créée.
) else (
    echo Base de données nouv_db déjà existante — ignorée.
)

REM ── Installation extension pgvector ──────────────────────────
echo Installation de l'extension pgvector...
"C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -p 5434 -d nouv_db -c "CREATE EXTENSION IF NOT EXISTS vector;" >nul 2>&1
"C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -p 5434 -d nouv_db -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" >nul 2>&1
echo OK

echo.
echo ============================================================
echo   Installation terminée !
echo ============================================================
echo.
echo Pour lancer le système :
echo.
echo   1. Lancer le backend :
echo      venv\Scripts\activate
echo      python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
echo.
echo   2. Ouvrir dans le navigateur :
echo      http://localhost:8000
echo.
echo   3. Scanner vos archives (première utilisation) :
echo      Aller sur http://localhost:8000/pipeline
echo      Cliquer sur "Scanner l'arborescence"
echo.
echo ============================================================
echo.
pause
