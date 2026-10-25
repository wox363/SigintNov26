# AMBER — Troubleshooting

## Backend won't start

**Symptom:** `start-amber.bat` says "Backend did not respond on 8001 after 20s".

1. Open `cmd`, navigate to the install folder, run `backend\amber-backend.exe` directly. Read the error in the console.
2. Common causes:
   - Mongo isn't up yet — wait 5s then retry.
   - `C:\AMBER-Data\` not writeable — check Windows ACLs on the data folder.
   - Antivirus quarantined `amber-backend.exe` — whitelist the install folder.

## MongoDB won't start

**Symptom:** Mongo log (`C:\AMBER-Data\logs\mongod.log`) shows `Address already in use`.

- Another Mongo is running. Run `tasklist | findstr mongod` and stop it, or change AMBER's port in `start-amber.bat` (`--port 27018`) and `MONGO_URL` accordingly.

**Symptom:** Mongo log shows `Permission denied`.

- The Windows user running `start-amber.bat` has no write access to `C:\AMBER-Data\mongo`. Right-click the folder → Properties → Security → grant Modify to the user.

## OCR returns nothing

**Symptom:** Image upload "succeeds" but no text extracted.

1. Check `/api/health` → `ocr.available`. If `false`, Tesseract is missing.
2. If `true` but still nothing: check the image quality. Tesseract needs ≥150 DPI, clear contrast. Phone screenshots usually work; faded photocopies don't.
3. AMBER's OCR is English-only by default. Non-Latin scripts (Hindi/Urdu/Punjabi text inside images) won't be transcribed.

## Geocoding shows blanks on the map

- AMBER ships **3,725 Indian places** offline (no internet). If your tower / village isn't in that set, no marker.
- Workaround: edit `backend\india_places_data.py` and add the place + lat/lng manually. Restart AMBER. (Recompile into the installer for permanent fix.)

## Upload fails with 413

- File > 50 MB.
- To raise the cap, before launching set: `set MAX_UPLOAD_MB=200` then `start-amber.bat`. Note: large files still load entirely into RAM during parsing — don't go above 200 MB on a 16 GB machine.

## Slow analysis on large CDR files

- Analysis runs on the same process as the API — heavy CPU work blocks other requests during processing.
- For the air-gapped single-machine model this is acceptable but visible. Don't open the dashboard mid-analysis.

## "needs re-analysis" banner won't clear

- Re-run analysis from the case page. If it still won't clear:
  - Open `http://127.0.0.1:8001/api/cases/<case_id>` and check `needs_reanalysis`, `last_data_change_at` vs `analyses.created_at`.
  - If timestamps are inconsistent, the data was changed during an analysis run. Re-run once more — it will sync.

## Browser shows old data after upload

- React caches the dashboard. Hit Ctrl+F5.

## Resetting everything (nuclear option)

1. Stop AMBER.
2. Move `C:\AMBER-Data\` to a backup name.
3. Launch AMBER — a clean Data folder is recreated empty.
4. To restore selectively: copy individual case backups from the old folder.

## How do I confirm AMBER never talks to the internet?

From the same machine, while AMBER is running:

```
netstat -an | findstr LISTENING
```

You should see only `127.0.0.1:8001` and `127.0.0.1:27017`. No `0.0.0.0` and no public addresses.

For outbound:

```
netstat -an | findstr ESTABLISHED
```

After uploading data and running analysis, there should be **no** connections to public IPs originating from `amber-backend.exe` or `mongod.exe`.

## Log locations

| Component | Log file |
|---|---|
| MongoDB | `C:\AMBER-Data\logs\mongod.log` |
| Backend (foreground) | console output of `start-amber.bat` |
| Backend (service) | Windows Event Viewer → Application logs, source `AMBER-Backend` |

## Getting help

If none of the above works, send the platform team:

1. Output of `http://127.0.0.1:8001/api/health` (paste the JSON).
2. Last 200 lines of `mongod.log`.
3. Steps that reproduce the issue.
4. Windows version (`winver`).
