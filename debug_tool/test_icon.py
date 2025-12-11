#!/usr/bin/env python3
"""Test if icon is embedded in the exe file"""

import os
import subprocess

def test_icon_in_exe():
    exe_path = "dist/TcpTool.exe"
    
    if not os.path.exists(exe_path):
        print(f"Error: {exe_path} not found! Please build the exe first.")
        return
    
    # Check file size - exe with icon should be larger
    file_size = os.path.getsize(exe_path)
    print(f"EXE file size: {file_size:,} bytes")
    
    # Try to extract icon info using PowerShell
    try:
        cmd = f'powershell -Command "Add-Type -AssemblyName System.Drawing; $icon = [System.Drawing.Icon]::ExtractAssociatedIcon(\'{exe_path}\'); Write-Host \'Icon size:\' $icon.Width \'x\' $icon.Height"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("Icon extraction result:", result.stdout.strip())
        else:
            print("Could not extract icon info")
    except Exception as e:
        print(f"Error checking icon: {e}")

if __name__ == "__main__":
    test_icon_in_exe()