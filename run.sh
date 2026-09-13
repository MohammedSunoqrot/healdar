#!/usr/bin/env bash
# Launch Healdar locally.
cd "$(dirname "$0")"
# The embedding model is already cached locally, so skip the Hub network check.
# Do NOT set this on HuggingFace Spaces — the model downloads on cold start there.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_VERBOSITY=error
export PYTHONIOENCODING=utf-8
exec .venv/bin/streamlit run src/app.py "$@"
