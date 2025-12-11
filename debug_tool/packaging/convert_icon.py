#!/usr/bin/env python3
"""Convert PNG icon to ICO format for PyInstaller"""

from PIL import Image
import os

def convert_png_to_ico():
    png_path = "packaging/icon.png"
    ico_path = "packaging/icon.ico"
    
    if not os.path.exists(png_path):
        print(f"Error: {png_path} not found!")
        return False
    
    try:
        # Open PNG image
        img = Image.open(png_path)
        
        # Convert to RGBA if not already
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Save as ICO with default 48x48 size
        img.save(ico_path, format='ICO', sizes=[(48,48)])
        print(f"Successfully converted {png_path} to {ico_path}")
        return True
        
    except Exception as e:
        print(f"Error converting icon: {e}")
        return False

if __name__ == "__main__":
    convert_png_to_ico()