#!/usr/bin/env bash
set -euo pipefail
cd /workspace/B-i-4.-B-N-TRONG-M-Y-T-NH
python3 -m venv /workspace/omr-clean-venv
/workspace/omr-clean-venv/bin/python -m pip install --disable-pip-version-check -r omr/requirements.txt
/workspace/omr-clean-venv/bin/python -m pip check
OMR_DATA_DIR="${OMR_DATA_DIR:-/workspace/omr-data}" /workspace/omr-clean-venv/bin/python -c 'from omr.store import init; init()'

command -v tesseract >/dev/null
command -v pdftoppm >/dev/null
mkdir -p /workspace/omr-ocr
if ! printf '%s  %s\n' '79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1' '/workspace/omr-ocr/vie.traineddata' | sha256sum --check --status; then
    curl --fail --silent --show-error --location https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/vie.traineddata --output /workspace/omr-ocr/vie.download
    printf '%s  %s\n' '79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1' '/workspace/omr-ocr/vie.download' | sha256sum --check
    mv /workspace/omr-ocr/vie.download /workspace/omr-ocr/vie.traineddata
fi
tesseract --tessdata-dir /workspace/omr-ocr --list-langs
