@echo off
title Inventory Monitor — Starting...
color 0A

echo.
echo  ============================================
echo   Inventory Monitoring System
echo   Starting all components...
echo  ============================================
echo.

:: Check we are in the right folder
if not exist "data\create_inventory.py" (
    echo  [ERROR] Cannot find data\create_inventory.py
    echo  Make sure you are running this from inside inventory_system\
    pause
    exit /b 1
)

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Make sure Python is installed and in your PATH.
    pause
    exit /b 1
)

:: Check FastAPI is installed
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installing FastAPI and Uvicorn...
    pip install fastapi uvicorn
)

:: Step 1 — Create fresh inventory
echo  [1/5] Creating fresh inventory.xlsx...
python data\create_inventory.py
if errorlevel 1 (
    echo  [ERROR] Failed to create inventory.xlsx
    pause
    exit /b 1
)
echo  [1/5] inventory.xlsx ready.
echo.

:: Step 2 — Index inventory into ChromaDB synchronously before browser opens
echo  [2/5] Indexing inventory into ChromaDB (please wait)...
echo  (Make sure Ollama is running in the system tray)
python rag\run_indexer_once.py
if errorlevel 1 (
    echo  [WARNING] Initial indexing failed.
    echo  Make sure Ollama is running then try again.
    echo  Continuing anyway...
    echo.
)
echo  [2/5] ChromaDB ready.
echo.

:: Step 3 — Start Simulator
echo  [3/5] Starting Simulator...
start "Inventory Simulator" cmd /k "cd /d %~dp0 && python data\simulator.py"
timeout /t 2 /nobreak >nul

:: Step 4 — Start RAG Indexer + Orchestrator
echo  [4/5] Starting RAG Indexer and Orchestrator...
start "RAG Indexer"  cmd /k "cd /d %~dp0 && python rag\indexer.py"
timeout /t 1 /nobreak >nul
start "Orchestrator" cmd /k "cd /d %~dp0 && python agents\orchestrator.py"
timeout /t 2 /nobreak >nul

:: Step 5 — Start Web Server
echo  [5/5] Starting Web Server...
start "Web Server" cmd /k "cd /d %~dp0 && python ui\server.py"
timeout /t 3 /nobreak >nul

echo.
echo  ============================================
echo   System is running!
echo.
echo   Dashboard: http://localhost:8000
echo.
echo   Aura is ready — ChromaDB was pre-loaded
echo   before the browser opened.
echo.
echo   To stop: close all 4 terminal windows
echo  ============================================
echo.

:: Open browser
start "" "http://localhost:8000"

pause
