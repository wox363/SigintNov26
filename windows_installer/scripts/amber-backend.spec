# amber-backend.spec — PyInstaller spec for the FastAPI backend.
# Run from the windows_installer\scripts directory via 02-freeze-backend.bat.

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# geonamescache ships its city DB as JSON files inside the package — must bundle them.
geonames_datas = collect_data_files("geonamescache")

a = Analysis(
    ["..\\..\\backend\\server.py"],
    pathex=["..\\..\\backend"],
    binaries=[],
    datas=[
        # Bundle the React static build INTO the EXE folder as frontend_dist/
        ("..\\..\\frontend\\build\\*", "frontend_dist"),
        ("..\\..\\frontend\\build\\static\\css\\*", "frontend_dist\\static\\css"),
        ("..\\..\\frontend\\build\\static\\js\\*", "frontend_dist\\static\\js"),
        ("..\\..\\frontend\\build\\static\\media\\*", "frontend_dist\\static\\media"),
        # Bundle backend data assets
        ("..\\..\\backend\\platform_db.json", "."),
        ("..\\..\\backend\\india_places_data.py", "."),
        # geonamescache cities JSON
        *geonames_datas,
    ],
    hiddenimports=[
        *collect_submodules("uvicorn"),
        *collect_submodules("motor"),
        *collect_submodules("pymongo"),
        "geocoder",
        "india_places_data",
        "geonamescache",
        "pdfplumber",
        "pypdfium2",
        "PIL.Image",
        "pytesseract",
        "imagehash",
        "scipy",
        "openpyxl",
        "msoffcrypto",
        "docx",
        "reportlab",
        "pptx",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "torch",
        "transformers",
        "google",
        "boto3",
        "litellm",
        "stripe",
    ],
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
    name="amber-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # show backend logs in a console window — easier for IT to debug
    disable_windowed_traceback=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="amber-backend",
)
