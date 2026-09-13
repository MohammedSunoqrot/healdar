#!/usr/bin/env bash
# deploy.sh — publish Healdar.
#
#   ./deploy.sh              commit and push to GitHub only
#   ./deploy.sh --hf         also publish to the public HuggingFace Space
#
# Publishing to HuggingFace is deliberately opt-in. `git add .` followed by an
# unconditional push to a public Space is a one-keystroke way to put untested
# work, or a corpus mid-rebuild, in front of real users.
set -euo pipefail

PUBLISH_HF=false
for arg in "$@"; do
    case "$arg" in
        --hf) PUBLISH_HF=true ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

if [ ! -f "src/app.py" ]; then
    echo "Error: run this script from the Healdar project root."
    exit 1
fi

# ── Pre-flight ───────────────────────────────────────────────────────────────
echo "Running checks..."

if ! python -m pytest tests -q; then
    echo "Tests failed — not deploying."
    exit 1
fi

if ! python eval/run_eval.py >/dev/null; then
    echo "Retrieval evaluation below threshold — not deploying."
    echo "Run 'python eval/run_eval.py' to see which metric regressed."
    exit 1
fi

# A pointer stub here means the vector store would ship broken, and the app
# would answer "no relevant information found" to every question.
python - <<'PY'
import sys
sys.path.insert(0, "src")
import config, vectorstore
stubs = vectorstore.find_lfs_pointers(config.DATA_DIR)
if stubs:
    print("Unresolved Git LFS pointers — run 'git lfs pull' first:")
    for p in stubs:
        print(f"  {p}")
    sys.exit(1)
PY

echo "Checks passed."

# ── Stage ────────────────────────────────────────────────────────────────────
git add -A

echo ""
echo "Files staged for commit:"
git status --short
echo ""

if git diff --cached --quiet; then
    echo "Nothing to commit — working tree is clean."
    exit 0
fi

read -rp "Commit message: " MSG
if [ -z "$MSG" ]; then
    echo "Aborted: commit message cannot be empty."
    exit 1
fi

git commit -m "$MSG"

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo ""
echo "Pushing to GitHub ($BRANCH)..."
git push origin "$BRANCH"
echo "  GitHub: OK"

# ── HuggingFace Space (public) ───────────────────────────────────────────────
if [ "$PUBLISH_HF" = false ]; then
    echo ""
    echo "Skipping HuggingFace — this Space is public."
    echo "When you have tested and want to publish:  ./deploy.sh --hf"
    exit 0
fi

if [ "$BRANCH" != "main" ]; then
    echo ""
    echo "Refusing to publish branch '$BRANCH' to the public Space."
    echo "Merge to main first."
    exit 1
fi

echo ""
echo "About to publish to the PUBLIC HuggingFace Space:"
echo "  https://huggingface.co/spaces/MohammedSunoqrot/healdar"
read -rp "Type 'publish' to confirm: " CONFIRM
if [ "$CONFIRM" != "publish" ]; then
    echo "Aborted."
    exit 1
fi

git push hf main
echo "  HuggingFace: OK"

echo ""
echo "Done."
echo "  GitHub:      https://github.com/MohammedSunoqrot/healdar"
echo "  HuggingFace: https://huggingface.co/spaces/MohammedSunoqrot/healdar"
