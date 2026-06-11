@echo off
pyinstaller.exe --onefile --clean --noconfirm --hidden-import=win32timezone --name OpcDaUaBridge bridge/bridge.py