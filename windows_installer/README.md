# AMBER — Windows Installer Build Pipeline

This folder contains everything needed to produce a **single-machine, offline, Windows installer** for AMBER.

The build must be run **once on a Windows 10/11 x64 machine** with internet access (only at build time — the resulting installer is fully offline). The output is a self-contained installer that the agency IT can run on an air-gapped target machine.

---

## What the final installer ships

```
C:\Program Files\AMBER\
├── backend\
│   ├── amber-backend.exe          (PyInstaller-frozen FastAPI, includes geonamescache data)
│   ├── platform_db.json
│   └── india_places_data.py
├── frontend\                      (React static build)
│   ├── index.html
│   ├── static\
│   └── ...
├── mongodb\                       (MongoDB Community 7.0 portable)
│   ├── bin\mongod.exe
│   └── data\                      (created on first run)
├── tesseract\                     (Tesseract 5.x portable)
│   ├── tesseract.exe
│   └── tessdata\eng.traineddata
├── start-amber.bat                (launches mongod + backend + opens browser)
├── stop-amber.bat
├── install-service.bat            (optional: register as Windows Service)
├── uninstall-service.bat
├── BACKUP-amber.bat               (mongodump → USB / external drive)
├── RESTORE-amber.bat              (mongorestore from a backup folder)
└── README.txt                     (one-page agency-IT cheat sheet)
```

The user double-clicks `start-amber.bat`. After ~10s, their default browser opens `http://127.0.0.1:3000`. No internet at any point.

---

## Build prerequisites (on the Windows BUILD machine, one-time)

1. **Windows 10 or 11 x64**, internet at build time only.
2. **Python 3.11.x** from python.org — tick "Add to PATH".
3. **Node.js 20 LTS** from nodejs.org.
4. **Yarn** — `npm install -g yarn`.
5. **Inno Setup 6** from jrsoftware.org (free).
6. **Git** (to pull the repo).

Then download the **three bundled third-party blobs** into `windows_installer\bin\`:

| File | Where | Size |
|---|---|---|
| `mongodb-windows-x86_64-7.0.x.zip` | mongodb.com/try/download/community → "Windows x64 ZIP" | ~250 MB |
| `tesseract-ocr-w64-setup-5.x.x.exe` | github.com/UB-Mannheim/tesseract/wiki | ~70 MB |
| `eng.traineddata` | github.com/tesseract-ocr/tessdata_best/blob/main/eng.traineddata | ~24 MB |

Place all three in `windows_installer\bin\`. The build script picks them up.

---

## Build steps

From a Windows `cmd.exe` (or PowerShell) opened in the repo root:

```bat
cd windows_installer\scripts
build-all.bat
```

This runs, in order:

1. `01-build-frontend.bat` — `cd frontend && yarn install && yarn build` with `REACT_APP_BACKEND_URL=http://127.0.0.1:8001` baked in.
2. `02-freeze-backend.bat` — PyInstaller produces `amber-backend.exe` (one-folder mode so geonamescache data + DLLs stay loose; much faster to launch than `--onefile`).
3. `03-stage-bundle.bat` — copies frontend build + frozen backend + extracted MongoDB + extracted Tesseract into `windows_installer\staging\AMBER\`.
4. `04-compile-installer.bat` — runs Inno Setup against `amber-installer.iss`, producing `AMBER_Setup_vX.Y.Z.exe` in `windows_installer\dist\`.

Total build time: ~5–8 minutes on a modern laptop.

The final `AMBER_Setup_vX.Y.Z.exe` is what you hand to agency IT.

---

## What agency IT does on the target machine

1. Copy `AMBER_Setup_vX.Y.Z.exe` to the air-gapped Windows machine (USB, internal share, etc.).
2. Run as Administrator. Accept defaults. Install path: `C:\Program Files\AMBER`.
3. Installer asks for a **Data folder** (default `C:\AMBER-Data`) — this is where cases, uploads, and the Mongo DB live. Should be on a drive the agency backs up.
4. Installer creates Start Menu shortcuts + an optional desktop icon.
5. Done. User clicks "AMBER" → backend starts, browser opens, ready.

The installer registers a **Windows Service** (optional, asked at install time) so AMBER restarts automatically on reboot.

---

## Network / firewall

The installer adds Windows Firewall rules **restricting Mongo (27017) and FastAPI (8001) to `127.0.0.1` only**. Nothing listens on any external interface. The frontend (`http://127.0.0.1:3000`) is served by FastAPI as static files — no separate web server needed.

---

## Updating an existing install

Hand over a newer `AMBER_Setup_vX.Y.Z.exe`. The installer detects the existing install and upgrades binaries **without touching the Data folder**. Cases are preserved.

---

## Files in this directory

```
windows_installer/
├── README.md                   (this file)
├── bin/                        (you drop MongoDB ZIP, Tesseract EXE, eng.traineddata here)
├── scripts/
│   ├── build-all.bat
│   ├── 01-build-frontend.bat
│   ├── 02-freeze-backend.bat
│   ├── 03-stage-bundle.bat
│   ├── 04-compile-installer.bat
│   ├── amber-backend.spec      (PyInstaller spec)
│   └── runtime/
│       ├── start-amber.bat
│       ├── stop-amber.bat
│       ├── install-service.bat
│       ├── uninstall-service.bat
│       ├── BACKUP-amber.bat
│       ├── RESTORE-amber.bat
│       └── README.txt          (ships inside the install)
├── amber-installer.iss         (Inno Setup script)
└── docs/
    ├── AGENCY_IT_GUIDE.md      (single-page deployment cheat sheet)
    └── TROUBLESHOOTING.md
```
