@echo off
REM Launch Healdar locally.
cd /d "%~dp0"
REM The embedding model is already cached locally, so skip the Hub network check.
REM Do NOT set this on HuggingFace Spaces - the model downloads on cold start there.
set HF_HUB_OFFLINE=1
set TRANSFORMERS_VERBOSITY=error
set PYTHONIOENCODING=utf-8
.venv\Scripts\streamlit run src\app.py %*
