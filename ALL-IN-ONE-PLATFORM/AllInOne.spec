# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files

SITE = "/Users/hakanficicilar/Library/Python/3.9/lib/python/site-packages"

datas = []
datas += collect_data_files("webview")

# templates, static klasörleri bundle içine ekle
datas += [("templates", "templates")]
datas += [("static",    "static")]
datas += [("app.py",    ".")]

# Platforma özgü
hiddenimports = [
    "webview",
    "webview.platforms.cocoa",
    "flask",
    "flask_cors",
    "jinja2",
    "werkzeug",
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AllInOne",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="AllInOne",
)

app = BUNDLE(
    coll,
    name="ALL-IN-ONE Platform.app",
    icon=None,
    bundle_identifier="com.allinone.investing",
    info_plist={
        "CFBundleName":           "ALL-IN-ONE Platform",
        "CFBundleDisplayName":    "ALL-IN-ONE Platform",
        "CFBundleVersion":        "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly":       False,
        "NSRequiresAquaSystemAppearance": False,
    },
)
