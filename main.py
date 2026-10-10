"""Einstieg für den PyInstaller-Build (.exe für Windows/Steam).

Normaler Start bleibt `python3 -m shadegunner`; dieser Einstiegspunkt ist nur
für `tools/build_windows.bat` / `shadegunner.spec` gedacht.
"""

from shadegunner.app import main

if __name__ == "__main__":
    main()
