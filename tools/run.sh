#!/usr/bin/env bash
# ShadeGunner starten.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG=/tmp/shadegunner.log

# KDE/Wayland lässt QOpenGLWidget mit unserem GLSL schwarz rendern. Über Xwayland
# (xcb) rendert es zuverlässig - nur wenn eine X-Anzeige da ist.
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -n "${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
fi

exec python3 -m shadegunner "$@" >"$LOG" 2>&1
