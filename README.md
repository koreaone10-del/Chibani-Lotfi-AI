# Chibani Lotfi AI v0.3

Mobile-first AI short-video studio optimized to remove unnecessary hops.

**Fast path:** Browser → one Render service → Colab/MoneyPrinterTurbo → Google Drive (final MP4 only).

### v0.3 changes
- Frontend and API are served by the same Render service.
- Browser never receives the private worker key.
- Worker polling is 2 seconds; MPT task polling is 1.5 seconds.
- Colab notebook is valid and clones both repositories in the correct order.
- Final MP4 is uploaded directly from MPT output; no duplicate Drive-mounted copy.
- MPT remains pinned to `436b0e9`.

### Deploy
1. Push the repository.
2. Render → Blueprint → select `deploy/render.yaml`.
3. Set `WORKER_API_KEY`.
4. Open the single Render URL.
5. In Colab Secrets add `CONTROL_API_URL`, `WORKER_API_KEY`, `PEXELS_API_KEY`, and optionally `GEMINI_API_KEY`.
6. Run `worker/MPT_Mobile_Cloud_Colab.ipynb`.
