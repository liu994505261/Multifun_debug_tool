@echo off
setlocal
REM Build single-file Windows executable for tcp_tool
REM Requires: PyInstaller installed (pip install pyinstaller)

pushd %~dp0\..

echo Converting icon...
python packaging/convert_icon.py

echo Building with system Python CLI (single-file)
python -m PyInstaller -F -w -n TcpTool qt_app.py --paths . ^
  --add-data "app;app" ^
  --collect-all pyside6 ^
  --icon icon.ico

if not exist dist\TcpTool.exe (
    echo CLI build failed, trying spec with system Python...
    python -m PyInstaller --noconfirm TcpTool_clean.spec
)
echo Build completed. Check: dist\TcpTool.exe
popd

pause

endlocal