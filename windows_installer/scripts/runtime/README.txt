AMBER — Offline SIGINT Forensic Platform
=========================================

QUICK START
-----------
1. Double-click  start-amber.bat
2. Wait ~10 seconds. Your browser opens automatically at http://127.0.0.1:8001/
3. To stop everything, close the console window OR run  stop-amber.bat

AUTO-START ON BOOT (optional, recommended for shared agency workstations)
-------------------------------------------------------------------------
Right-click  install-service.bat  ->  Run as Administrator
AMBER will then start automatically every time the machine boots.
To remove:  right-click uninstall-service.bat  ->  Run as Administrator

BACKUP
------
BACKUP-amber.bat  <destination_folder>
Example:  BACKUP-amber.bat D:\AMBER-Backups
Creates a timestamped folder containing the full Mongo dump + WhatsApp data.
Copy the folder to an external drive for safekeeping.

RESTORE
-------
RESTORE-amber.bat  <backup_folder>
This OVERWRITES the current database. Asks for YES confirmation.

WHERE THINGS LIVE
-----------------
- Install:      C:\Program Files\AMBER\
- Cases & DB:   C:\AMBER-Data\
- Logs:         C:\AMBER-Data\logs\
- WhatsApp:     C:\Program Files\AMBER\backend\whatsapp_data\

NETWORK
-------
AMBER listens ONLY on 127.0.0.1 (localhost). Nothing is reachable from the
network or the internet. No data ever leaves this machine.

SUPPORT
-------
If something doesn't work:
1. Open http://127.0.0.1:8001/api/health — every subsystem reports its status.
2. Check the logs at C:\AMBER-Data\logs\
3. Try running start-amber.bat from a cmd window — the console output usually
   tells you exactly what's failing.
