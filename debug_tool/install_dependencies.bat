@echo off
echo Activating virtual environment...
call .\venv\Scripts\activate.bat
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Installation complete!
echo You can now run the application using run_qt.bat
pause