#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-kindle_app}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

if ! command -v conda >/dev/null 2>&1; then
    echo "conda was not found in PATH. Install Miniconda/Anaconda first." >&2
    exit 1
fi

if conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
    conda env update -n "$ENV_NAME" -f environment.yml --prune
else
    conda env create -n "$ENV_NAME" -f environment.yml
fi

conda run -n "$ENV_NAME" python -m pip install --force-reinstall --no-deps -e .
conda run -n "$ENV_NAME" python -c "import kindle_vocab_app; print('kindle_vocab_app import ok:', kindle_vocab_app.__file__)"
conda run -n "$ENV_NAME" npm install
conda run -n "$ENV_NAME" npm rebuild esbuild
conda run -n "$ENV_NAME" python -c "import nltk; [nltk.download(package, quiet=True) for package in ('wordnet', 'omw-1.4', 'averaged_perceptron_tagger_eng', 'punkt_tab')]"
conda run -n "$ENV_NAME" kindle-vocab-doctor

echo ""
echo "Setup complete."
echo "Run:"
echo "  conda activate $ENV_NAME"
echo "  kindle-vocab-app"
