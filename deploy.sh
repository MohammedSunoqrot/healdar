#!/usr/bin/env bash
# deploy.sh — commit and push Healdar to GitHub + HuggingFace Spaces
set -euo pipefail

# ── Sanity check ──────────────────────────────────────────────────────────────
if [ ! -f "src/app.py" ]; then
    echo "Error: run this script from the Healdar project root."
    exit 1
fi

# ── Stage all changes ─────────────────────────────────────────────────────────
git add .

# ── Show what will be committed ───────────────────────────────────────────────
echo ""
echo "Files staged for commit:"
git status --short
echo ""

# ── Bail if there is nothing new ─────────────────────────────────────────────
if git diff --cached --quiet; then
    echo "Nothing to commit — working tree is clean."
    exit 0
fi

# ── Commit message ────────────────────────────────────────────────────────────
read -rp "Commit message: " MSG
if [ -z "$MSG" ]; then
    echo "Aborted: commit message cannot be empty."
    exit 1
fi

git commit -m "$MSG"

# ── Push to GitHub ────────────────────────────────────────────────────────────
echo ""
echo "Pushing to GitHub..."
if git push origin main; then
    echo "  GitHub: OK"
else
    echo "  GitHub: FAILED"
    exit 1
fi

# ── Push to HuggingFace Spaces ────────────────────────────────────────────────
echo ""
echo "Pushing to HuggingFace Spaces..."
if git push hf main; then
    echo "  HuggingFace: OK"
else
    echo "  HuggingFace: FAILED"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Done — both remotes updated."
echo "  GitHub:       https://github.com/MohammedSunoqrot/healdar"
echo "  HuggingFace:  https://huggingface.co/spaces/MohammedSunoqrot/healdar"
