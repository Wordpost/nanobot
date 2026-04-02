@echo off
pushd "%~dp0"
echo [Nanobot] Initializing Forensic Viewer Environment...
python -m venv venv
echo [Nanobot] Activating Virtual Environment...
call venv\Scripts\activate.bat
echo [Nanobot] Installing requirements (FastAPI)...
pip install -r requirements.txt
echo [Nanobot] Setup Complete. Use run.bat to start.
popd
pause
