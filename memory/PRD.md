# AMBER — SIGINT Forensic Platform (PRD)

## Original Problem Statement
Design and develop a software system that ingests IPDR, CDR datasets and WhatsApp Export ZIPs to automatically perform structured intelligence-style analysis. Detect patterns of financial activity, encrypted communication, file transfers, and shared contact networks. Assign risk scores, generate investigator-ready reports, support cross-case correlation. Strictly offline, rule-based logic, image OCR, geospatial mapping, soft-delete with undo, async background processing, downloadable reports (DOCX/PDF), and a visual briefing presentation module for senior officers.

## Operating Contract
- **Truthful / blunt** — no hallucinated capabilities.
- **Strictly offline** — no cloud APIs in any pipeline.
- **Deployment model**: each agency runs its own air-gapped Windows install. No shared DB.

## Deployment Architecture (Feb 2026)
- **Target**: Windows 10/11 x64, air-gapped.
- **Distribution**: Single `AMBER_Setup_v1.0.0.exe` (~500–700 MB).
- **Bundles**: MongoDB 7.0 portable, Tesseract 5.x + `eng.traineddata`, frozen Python backend (PyInstaller), React static build, geonamescache India dataset.
- **Network**: Backend on `127.0.0.1:8001`, Mongo on `127.0.0.1:27017`. Windows Firewall rules block external access.
- **Build pipeline**: `windows_installer/scripts/build-all.bat` on a Windows build machine produces the final installer EXE.

## Implemented (live)
- CDR & IPDR ingestion (PDF via pdfplumber, robust tabular parsing)
- Analysis engine: contact graph, risk scoring, SIM/IMSI changes, cell co-location, bulk-data alerts
- Cross-case comparison with alias detection
- WhatsApp ZIP triage Phase 1 (per-case SQLite, OCR, perceptual dedup, financial-keyword highlighter)
- Soft-delete with 3-min undo + background purger
- DOCX / PDF / PPTX report streaming
- **Offline India geocoder** (replaces Nominatim) — 3,725 places, no internet (Feb 2026)
- **50 MB upload cap** with streaming size check (HTTP 413 on overflow) (Feb 2026)
- **`/api/health` diagnostic endpoint** (Feb 2026)
- **Windows installer pipeline** — build scripts, PyInstaller spec, Inno Setup script, IT docs (Feb 2026)
- **FastAPI serves React static build** when `frontend_dist/` is present (single-binary mode)
- Pytest suite: 105/105 passing

## Architecture
```
/app/backend/
  server.py                FastAPI, /api/health, 50 MB cap, static frontend mount
  parsers.py               PDF / regex / pdfplumber
  analysis_engine.py       Rule-based engine (uses offline geocoder)
  geocoder.py              Offline India geocoder (3,725 places)
  india_places_data.py     Curated J&K + sensitive places
  compare_engine.py        Cross-case correlation
  whatsapp_parser.py       WA ZIP ingestion
  whatsapp_engine.py       WA analysis
  report_generator.py      DOCX/PDF
  briefing_deck.py         Senior-officer PPTX
  tests/                   105 pytest cases

/app/frontend/             React UI (built to frontend/build/ for installer)

/app/windows_installer/
  README.md                Build pipeline overview
  bin/                     Drop MongoDB ZIP, Tesseract EXE, eng.traineddata here
  scripts/
    build-all.bat          Master build
    01-build-frontend.bat
    02-freeze-backend.bat
    03-stage-bundle.bat
    04-compile-installer.bat
    amber-backend.spec     PyInstaller spec
    runtime/               Scripts shipped INSIDE the install
      start-amber.bat
      stop-amber.bat
      install-service.bat  Optional NSSM-based Windows Service
      uninstall-service.bat
      BACKUP-amber.bat     mongodump to USB
      RESTORE-amber.bat
      README.txt
  amber-installer.iss      Inno Setup script (firewall rules, data dir, services)
  docs/
    AGENCY_IT_GUIDE.md
    TROUBLESHOOTING.md
```

## Key API Endpoints
- `GET /api/health` — geocoder/OCR/upload-cap status (NEW)
- `POST /api/cases`, `GET /api/cases`, `DELETE /api/cases/{id}`
- `POST /api/cases/{id}/upload` — 50 MB cap, returns 413 on overflow
- `POST /api/cases/{id}/uploads/{upload_id}/reupload`
- `DELETE /api/cases/{id}/uploads/{upload_id}` — soft-delete + undo
- `POST /api/compare`, `GET /api/compare/{id}/report/{pdf|docx}`
- `POST /api/cases/{id}/whatsapp/upload`
- `GET /api/briefing-deck` — auto-generated PPTX

## Audit Findings (Feb 2026)

### Closed in this session
- 🟢 Nominatim/internet dependency → offline India geocoder
- 🟢 No upload size limit → 50 MB streaming cap
- 🟢 No Windows installer → full pipeline built
- 🟢 `REACT_APP_BACKEND_URL` baked to preview → installer overrides to `http://127.0.0.1:8001`
- 🟢 FastAPI couldn't serve static React → `frontend_dist/` mount added

### Pre-Launch Security Audit — closed Nov 2026
- 🟢 **SEC-001 (P1) fixed**: Removed PostHog session-recording, `assets.emergent.sh/emergent-main.js`, and Google Fonts CDN from `frontend/public/index.html`. Verified served HTML is clean. Prevents classified data leaking via session replay if the air-gap ever fails.
- 🟢 **Global security headers** middleware added (`server.py`): strict CSP (no external origins), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` locks down camera/mic/geo/payment/usb.
- 🟢 **FastAPI `/docs`, `/redoc`, `/openapi.json` disabled** by default. Operators who need them set `AMBER_EXPOSE_DOCS=1` env var.
- 🟢 **ZIP-bomb protection** in `whatsapp_parser.py`: per-entry 200x decompression ratio cap + 2 GB total decompressed cap.
- 🟢 **Evidence writes routed through `_persist_evidence_locally()`** with offline-by-design docstring.
- 🟢 **Dependency prune** (Nov 2026): removed stripe, openai, litellm, boto3, google-genai, google-auth, google-generativeai, botocore, PyJWT, python-jose, passlib, bcrypt, emergentintegrations (13 heavy unused packages). requirements.txt 145 → 139 lines.
- 🟢 **Audit log** (`audit_log.py`): append-only `db.audit` collection, writes operator (Windows USERNAME), host, action, target. Wired into 10 mutating routes (case/upload CRUD, compare, reports, briefing). `GET /api/audit` with case_id/action/operator/limit filters.
- 🟢 **Pagination** (`GET /api/cases`): new envelope `{total, skip, limit, cases}` + `?q=` substring filter. Per-case endpoints (uploads/evidence/WA-uploads) have ceilings raised 500→10,000 with explicit newest-first sort. Frontend updated with forward-compatible parsing.
- 🟢 **`pytest.ini`** added to pin asyncio mode.
- **118/118 tests passing** after all hardening changes.

### Known preview-only artefact (ignore on Windows install)
- Preview environment's Cloudflare edge injects `fonts.googleapis.com` + `static.cloudflareinsights.com` tags that are **NOT in our code**. Confirmed by curl'ing the dev server directly. Windows install serves `frontend_dist/` via FastAPI which does not inject anything; CSP would block them at the browser even if they appeared.

### Still open (P1 — Tier 2)
- 100/500 silent `to_list` truncations on cases/uploads/evidence
- Geocode cache not persisted to Mongo
- Risk-scoring rubric not documented in report appendix
- Stale `/presentation` page (old web deck) — drift risk vs auto-generated PPTX
- No per-officer audit log

### Tier 3 (hardening)
- Analysis still runs on the same event loop (CPU-blocking)
- No first-run wizard
- No diagnostic-export ZIP button
- Installer not code-signed

### Out of scope for now
- WhatsApp Phase 2/3 (translation, voice notes, TZ selector)
- JWT / multi-user auth
- Multi-tenant or shared-server deployment

## Credentials
- PDF test password: `cms@13rr`

## Build Output
- `/app/AMBER_Briefing_YYYYMMDD.pptx` — 12-slide briefing deck (regenerated on demand)
- `windows_installer/dist/AMBER_Setup_v1.0.0.exe` — produced by `build-all.bat` on a Windows build machine
