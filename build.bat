@echo off
rem NexEnvanter yerel derleme (Windows). Gereken: Python 3.12+ (python.org, PATH'e ekli)
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (python -m venv .venv || goto :err)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements-dev.txt || goto :err
python -m pytest -q || goto :err
python build\make_assets.py || goto :err
pyinstaller NexEnvanter.spec --noconfirm --clean || goto :err
echo.
echo Tamam: dist\NexEnvanter.exe
goto :eof
:err
echo Derleme BASARISIZ.
exit /b 1
