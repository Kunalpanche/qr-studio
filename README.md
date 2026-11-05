# QR Studio

Free, self-hosted static QR generator built with React/Vite and FastAPI. No redirects, scans, or QR content are stored.

## Run locally

```powershell
npm install
pip install -r requirements.txt
npm run dev
uvicorn api.index:app --reload --port 8000
```

Vite proxies are unnecessary in production: the app calls `/api/generate`, which is routed to FastAPI on Vercel. For local frontend-only development, run FastAPI on port 8000 and add a Vite proxy if desired.

## Deploy

Import this repository into Vercel. The included `vercel.json` builds the Vite app and deploys `api/index.py` as a Python serverless function. Uploaded logos only travel in the generation request and are never persisted.

## Test checklist

Generate URL, Google Form, Wi‑Fi, UPI and logo QR codes; download PNG/SVG/PDF; verify scans on a phone. Use high error correction for logos and maintain strong foreground/background contrast.
