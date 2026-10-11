# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für ShadeGunner (Windows/macOS-Build, u. a. für Steam).

Build:  tools\\build_windows.bat    ->   dist\\ShadeGunner\\ShadeGunner.exe

PyInstaller bündelt Python, PyQt6 (inkl. Qt-Plattform-Plugin) und - falls
installiert - numpy. Der Soundtrack wird beim ersten Start vom Spiel selbst in
einem Hilfsprozess erzeugt (siehe shadegunner/audio.py).

Hinweis: Eine Windows-.exe lässt sich nur *auf* Windows bauen.
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icons', 'assets/icons')],   # Fenster-Icon (shadegunner/app.py)
    hiddenimports=[],
    hookspath=[],
    excludes=['tkinter', 'PyQt6.QtQuick', 'PyQt6.QtQml', 'PyQt6.QtWebEngineCore'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShadeGunner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # kein Konsolenfenster
    icon='assets/icons/shadegunner.ico',   # Explorer/Taskleiste (tools/make_brand.py)
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ShadeGunner',
)
