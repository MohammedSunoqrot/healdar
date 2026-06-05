#!/usr/bin/env bash
cd "$(dirname "$0")"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_VERBOSITY=error
.venv/bin/streamlit run src/app.py
