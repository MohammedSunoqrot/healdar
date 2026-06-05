@echo off
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_VERBOSITY=error
.venv\Scripts\streamlit run src\app.py
