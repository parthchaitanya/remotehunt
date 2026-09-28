# Showcase RemoteHunt publicly (free)

This guide publishes a **public demo**: the real app running with a fictional candidate ("Asha Verma") and a snapshot of about 300 real public job postings. Your resume, tracker, Gmail and API keys are **not** part of it.

| Piece | Free service | What it does |
|---|---|---|
| Code | **GitHub** (public repo) | Portfolio link, README with screenshots |
| CI | **GitHub Actions** (`.github/workflows/ci.yml`) | Runs the pytest suite, builds the UI and smoke-tests the demo image on every push |
| Live demo | **Render** free web service (`render.yaml` + `Dockerfile.demo`) | `https://remotehunt-demo.onrender.com` |

How the demo differs from your private instance:

| | Your instance | Public demo |
|---|---|---|
| Data | your resume, real searches | fictional resume, job snapshot, re-seeded on each start |
| Matching model | all-MiniLM-L6-v2 (torch, ~2 GB RAM) | lightweight hashing embedder (<512 MB RAM, fits free tiers) |
| Gmail, live searches, uploads, digest sending | on | **disabled** (a 403 explains why), so visitors can't burn API rate limits or leave personal data |
| Groq AI | on | off (templates), so nobody spends your key |

## 1. Check that nothing private gets published

`.gitignore` already excludes `.env` (all your keys), `data/` (database, resume versions, tokens) and every `*.pdf` / `*.docx` (your resume files). Your Gmail address now lives in `.env` as `GMAIL_ADDRESS`, not in `config/profile.yaml`.

Before the first push, run:

```bash
cd ~/remotehunt
git add -A
git status --short | grep -Ei "\.env$|data/|\.pdf|\.docx|client_secret" && echo "STOP - private file staged" || echo "clean"
```

## 2. Push to GitHub

1. Create an empty **public** repo at <https://github.com/new> named `remotehunt`. Don't add a README.
2. Push the project:
   ```bash
   cd ~/remotehunt
   git add -A
   git commit -m "RemoteHunt: remote job-search assistant"
   git branch -M main
   git remote add origin https://github.com/<your-username>/remotehunt.git
   git push -u origin main
   ```
3. Open the repo's **Actions** tab. The CI run (backend tests, frontend build, demo image smoke test) should go green in about 5 minutes.

## 3. Deploy the demo on Render (free)

1. Sign up at <https://render.com> with GitHub. **No card is needed** for free web services.
2. Go to **New + → Blueprint**, pick the `remotehunt` repo, then click **Apply**. Render reads `render.yaml` and builds `Dockerfile.demo`, which takes about 5–8 minutes.
3. Open the URL Render gives you, e.g. `https://remotehunt-demo.onrender.com`.
4. Put the link in the README (the *Live demo* line near the top) and on your resume or LinkedIn.

Free-tier behaviour:
- **Sleeping:** the service sleeps after 15 minutes without traffic. The first visit after that takes about 30–50 seconds to wake it, then it's fast.
- **Updates:** every push to `main` redeploys automatically.

### Alternatives (same `Dockerfile.demo`, no changes)

- **Koyeb** (free, no card): *Create Web Service → GitHub → Dockerfile* `Dockerfile.demo`, port `8000`.
- **Railway**: *New Project → Deploy from GitHub*, set the variable `RAILWAY_DOCKERFILE_PATH=Dockerfile.demo`. Railway now gives trial credit only, so it isn't free long-term.
- **Hugging Face Spaces** (free): create a *Docker* Space and push the repo with `Dockerfile.demo` renamed to `Dockerfile`. Add `app_port: 8000` in the Space README header.

## 4. Refresh the demo's job snapshot (optional)

The demo jobs come from your local database. Only job-posting fields are exported, never your resume, tracker or settings.

```bash
cd ~/remotehunt/backend
../.venv/bin/python scripts/export_demo_jobs.py
git add app/demo_data/jobs.json.gz && git commit -m "Refresh demo jobs" && git push
```

## Run the demo locally

```bash
docker build -f Dockerfile.demo -t remotehunt-demo .
docker run --rm -p 8000:8000 remotehunt-demo      # http://localhost:8000
```
