# Architecture v0.3

Browser → Render (FastAPI + frontend) → private worker key → Colab → localhost MoneyPrinterTurbo → final MP4 → Google Drive.

The browser has no privileged key and there is only one public web service. Intermediate render assets never travel through Render.
