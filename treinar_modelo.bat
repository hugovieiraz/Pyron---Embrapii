@echo off
rem Pyron: treinar um modelo no terminal. Arraste o .zip exportado do CVAT sobre este arquivo.
chcp 65001 >nul
title Pyron - Treinar modelo
cd /d "%~dp0"
".venv\Scripts\python.exe" -m ml.assistente %1
