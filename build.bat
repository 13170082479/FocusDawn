@echo off
setlocal
cd /d %~dp0
python -m PyInstaller --noconfirm --onefile --windowed --icon "assets\ui\app_icon.ico" --name FocusDawn --add-data "README.md;." --add-data "requirements.txt;." --add-data "assets;assets" main.py
endlocal
