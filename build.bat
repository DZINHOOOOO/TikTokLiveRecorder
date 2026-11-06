@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 goto fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --icon assets\recorder.ico --add-data "assets\recorder.ico;assets" --add-data "release_config.json;." --name TikTokLiveRecorder app.py
if errorlevel 1 goto fail
py make_checksum.py
if errorlevel 1 goto fail
echo.
echo Pronto! Publique no GitHub Releases:
echo dist\TikTokLiveRecorder.exe
echo dist\TikTokLiveRecorder.exe.sha256
pause
exit /b 0
:fail
echo Falha ao compilar. Veja o erro acima.
pause
exit /b 1
