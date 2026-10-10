#!/usr/bin/env bash
# ShadeGunner starten.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 -m shadegunner "$@"
