# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

APP_NAME = 'SEPA Stock Scanner'
SRC_DIR   = '.'

a = Analysis(
    ['desktop_app.py'],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        ('templates',  'templates'),
        ('static',     'static'),
        ('*.py',       '.'),
        ('*.csv',      '.'),
    ],
    hiddenimports=[
        # Flask ecosystem
        'flask', 'flask_cors', 'jinja2', 'werkzeug',
        'werkzeug.routing', 'werkzeug.serving',
        # Data
        'pandas', 'numpy', 'yfinance', 'requests',
        'pandas.io.formats.style',
        # PyWebView backends
        'webview', 'webview.platforms',
        # App modules
        'sepa_scanner', 'universal_scanner', 'backtest_engine',
        'sepa_signal_engine', 'twelvedata_client', 'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Konsol penceresi açma
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name=APP_NAME + '.app',
    icon=None,           # 'icon.icns' varsa buraya yaz
    bundle_identifier='com.sepa.stockscanner',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion':            '1.0.0',
        'NSHighResolutionCapable':    True,
        'NSRequiresAquaSystemAppearance': False,
    },
)
