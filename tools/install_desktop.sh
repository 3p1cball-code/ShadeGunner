#!/usr/bin/env bash
# ShadeGunner ins Startmenü eintragen (Linux, nur für den aktuellen Benutzer, kein root).
#
#   - Icons nach ~/.local/share/icons/hicolor/<n>x<n>/apps/shadegunner.png
#   - Menü-Eintrag ~/.local/share/applications/shadegunner.desktop
#     (Pfade zeigen auf *diesen* Checkout - egal wo er liegt)
#
# Entfernen:  tools/install_desktop.sh --uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor"
SIZES="16 24 32 48 64 128 256 512"

refresh() {
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true
    # nur auffrischen, wenn es schon einen Cache gibt (sonst keinen neuen anlegen)
    [ -f "$ICONS/icon-theme.cache" ] && command -v gtk-update-icon-cache >/dev/null \
        && gtk-update-icon-cache -q -t "$ICONS" || true
    command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$APPS/shadegunner.desktop"
    for s in $SIZES; do rm -f "$ICONS/${s}x${s}/apps/shadegunner.png"; done
    refresh
    echo "ShadeGunner aus dem Menü entfernt."
    exit 0
fi

for s in $SIZES; do
    src="$ROOT/assets/icons/shadegunner-$s.png"
    [ -f "$src" ] || { echo "fehlt: $src (tools/make_brand.py icons)"; exit 1; }
    install -Dm644 "$src" "$ICONS/${s}x${s}/apps/shadegunner.png"
done

mkdir -p "$APPS"
cat >"$APPS/shadegunner.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ShadeGunner
GenericName=Cyberpunk Side-Scroller
Comment=16-color Blade Runner side-scroller (Bayer dither + CRT)
Comment[de]=16-Farben Blade-Runner-Sidescroller (Bayer-Dither + CRT)
Exec="$ROOT/tools/run.sh"
Path=$ROOT
Icon=shadegunner
Terminal=false
Categories=Game;ActionGame;
Keywords=blade runner;cyberpunk;replicant;pixel;retro;
StartupWMClass=ShadeGunner
EOF
chmod 644 "$APPS/shadegunner.desktop"
refresh
echo "Installiert: $APPS/shadegunner.desktop (Icon 'shadegunner', Start: $ROOT/tools/run.sh)"
