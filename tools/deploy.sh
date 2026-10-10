#!/usr/bin/env bash
# ShadeGunner: Dev-Checkout -> Run-Maschine spiegeln.
# Aufruf: tools/deploy.sh   (Ziel per SHADEGUNNER_DEST überschreibbar)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${SHADEGUNNER_DEST:-nobara:/home/alex/ShadeGunner/}"
SSHCFG="${SHADEGUNNER_SSHCFG:-/home/ariedel/.ssh/config}"

rsync -az --delete \
  --exclude '__pycache__/' --exclude '*.pyc' --exclude 'data/' \
  -e "ssh -F ${SSHCFG}" \
  "${HERE}/" "${DEST}"

echo "deployed: ${HERE} -> ${DEST}"
