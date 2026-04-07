@echo off
title Inventory Monitor — Stopping...
echo.
echo  Stopping all Inventory Monitor components...
echo.

taskkill /FI "WINDOWTITLE eq Inventory Simulator*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RAG Indexer*"          /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Orchestrator*"          /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Web Server*"            /F >nul 2>&1

echo  All components stopped.
echo.
timeout /t 2 /nobreak >nul