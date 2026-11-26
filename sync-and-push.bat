@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==================================================
echo   FEAR Legion - AION 2 Auto Sync ^& Push to GitHub
echo ==================================================

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Dang tao moi truong Python (.venv) lan dau...
    python -m venv .venv
    ".venv\Scripts\pip.exe" install playwright
    ".venv\Scripts\playwright.exe" install chromium
)

echo [2/4] Dang lay du lieu moi nhat tu aion2index.com...
".venv\Scripts\python.exe" scripts\update_data.py
if errorlevel 1 (
    echo [LOI] Khong lay duoc du lieu. Nhan phim bat ky de thoat.
    pause >nul
    exit /b 1
)

echo [3/4] Dang dong bo len GitHub...
git add data/
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "chore(data): sync latest member stats"
    git push origin main
    echo [4/4] Hoan tat! GitHub Pages se cap nhat sau ~1 phut.
) else (
    echo [4/4] Khong co thay doi moi so voi ban hien tai.
)

pause
