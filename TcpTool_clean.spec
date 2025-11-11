# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['qt_app.py'],
    # 确保包含源码根目录，以正确发现 app 包
    pathex=['.'],
    binaries=[],
    datas=[],
    # 显式包含各模块，避免打包时遗漏
    hiddenimports=[
        'app.base_comm',
        'app.tcp_tab',
        'app.udp_tab',
        'app.serial_tab',
        'app.rs485_tab',
        'app.crc_tab',
        'app.esp32_log_tab',
        'app.crc_utils',
        'app.__init__'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TcpTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)