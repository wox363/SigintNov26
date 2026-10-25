# AMBER — Agency IT Deployment Guide

**Audience:** Agency IT / sysadmin installing AMBER on a single Windows workstation.
**Time required:** ~10 minutes.
**Internet at install or run time:** **None required.**

---

## 1. What you receive from the platform team

A single file:

```
AMBER_Setup_v1.0.0.exe
```

Size: roughly **500–700 MB** (it bundles MongoDB, Tesseract OCR, and the entire AMBER application).

Transfer it to the target machine via the agency's normal channel (USB, internal share, etc.).

---

## 2. Target machine prerequisites

| Item | Requirement |
|---|---|
| OS | Windows 10 x64 (1809+) or Windows 11 x64 |
| RAM | 8 GB minimum, 16 GB recommended |
| Disk | 10 GB free for the install + headroom for case data |
| Account | Administrator (to install services + firewall rules) |
| Network | **None.** Machine can be fully air-gapped. |

No Python, no Node, no MongoDB pre-installation — the installer ships everything.

---

## 3. Install

1. Right-click `AMBER_Setup_v1.0.0.exe` → **Run as administrator**.
2. Accept the install location (default `C:\Program Files\AMBER`).
3. Choose the **Data folder** (default `C:\AMBER-Data`). Use a drive that gets backed up.
4. On the **Tasks** screen, decide:
   - ✅ **Create a desktop icon** — recommended.
   - ⬜ **Install AMBER as a Windows Service** — tick this if the workstation is shared by multiple officers and you want AMBER to auto-start at boot. Leave unticked for single-user laptops.
5. Click **Install**. Wait ~1 minute.
6. Open `README.txt` when prompted (or skip — it's also at `C:\Program Files\AMBER\README.txt`).

The installer automatically:
- Drops everything under `C:\Program Files\AMBER\`
- Creates `C:\AMBER-Data\` for cases, database, logs
- Adds Windows Firewall rules **blocking** port 27017 (Mongo) and 8001 (backend) from any IP other than `127.0.0.1`
- Optionally registers two Windows Services: `AMBER-Mongo`, `AMBER-Backend`

---

## 4. First launch

Double-click **AMBER** on the desktop (or run `start-amber.bat` from the install folder).

A console window opens showing the startup sequence:

```
[1/3] Starting MongoDB on 127.0.0.1:27017 ...
[2/3] Starting AMBER backend on 127.0.0.1:8001 ...
[3/3] Opening AMBER in your browser ...
```

Your default browser opens at `http://127.0.0.1:8001/`.

**To stop AMBER**, close the console window OR run `stop-amber.bat`.

---

## 5. Verify everything works

Open this URL in the browser to see a self-check:

```
http://127.0.0.1:8001/api/health
```

You should see:

```json
{
  "service": "AMBER backend",
  "geocoder": { "total_indexed_places": 3725, "country_scope": "India only", "internet_required": false },
  "ocr": { "available": true, "version": "5.x" },
  "max_upload_mb": 50,
  "offline_only": true
}
```

If `"ocr.available": false`, Tesseract failed to install — re-run the installer or open a ticket with the platform team.

---

## 6. Backups

**Why this matters:** AMBER stores everything on the local disk. A drive failure = total data loss. The agency MUST back up.

```bat
cd "C:\Program Files\AMBER"
BACKUP-amber.bat  D:\AMBER-Backups
```

This creates `D:\AMBER-Backups\amber-backup-YYYYMMDD-HHMM\` containing:
- `mongo\` — full database dump (`mongodump`)
- `whatsapp_data\` — WhatsApp per-case SQLite + media

Schedule this in Windows Task Scheduler to run nightly to an external drive.

To **restore**: `RESTORE-amber.bat D:\AMBER-Backups\amber-backup-...`

---

## 7. Updating AMBER

When the platform team sends a new `AMBER_Setup_vX.Y.Z.exe`:

1. Stop AMBER (`stop-amber.bat` or stop the services).
2. Run the new installer as Administrator. It detects the existing install and **upgrades binaries only**. The `C:\AMBER-Data\` folder is untouched.
3. Launch again.

Cases, uploads, reports — all preserved.

---

## 8. Uninstall

Control Panel → Programs → AMBER → Uninstall.

The uninstaller removes the application and the firewall rules. **It does NOT touch `C:\AMBER-Data\`** — you must delete that folder manually if you also want to destroy all case data.

---

## 9. What AMBER does NOT do

- It does **not** call the internet. Ever. Confirm with `netstat -an | findstr ":8001 :27017"` — both should show `127.0.0.1` only.
- It does **not** share data between machines. Each install is isolated. No cross-machine sync.
- It does **not** require a user account / login. Anyone with access to the Windows account can use it. Use Windows account permissions to control access.

---

## 10. Quick troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows "can't reach 127.0.0.1:8001" | Backend didn't start. Check `C:\AMBER-Data\logs\` and re-run `start-amber.bat` from a `cmd` window to see the error. |
| Health endpoint shows `ocr.available: false` | Tesseract wasn't bundled. Re-install. |
| Upload fails with "File exceeds 50 MB" | Split the file, or set `MAX_UPLOAD_MB=200` (or whatever) as an environment variable before launch. |
| Map / geocoding shows no markers | The place name isn't in the 3,725-entry India dataset. Geocoding is by design India-only. |
| "Port 27017 already in use" | Another MongoDB on the machine. Stop it before launching AMBER. |

Full troubleshooting list: `TROUBLESHOOTING.md` (next to this file).
