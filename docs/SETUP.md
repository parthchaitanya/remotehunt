# RemoteHunt – setup guide

RemoteHunt runs on your own machine. It pulls remote jobs from official APIs, RSS feeds and your own Gmail job alerts, scores them against your resume, and helps you tailor documents. It never applies for you, never sends email to anyone but you, and never scrapes websites.

- [1. Prerequisites](#1-prerequisites)
- [2. Install and run locally](#2-install-and-run-locally)
- [3. Google Cloud OAuth for Gmail](#3-google-cloud-oauth-for-gmail)
- [4. API keys](#4-api-keys)
- [5. Run with Docker](#5-run-with-docker)
- [6. Configuration files](#6-configuration-files)
- [7. Schedules and rate limits](#7-schedules-and-rate-limits)
- [8. Privacy and safety rules](#8-privacy-and-safety-rules)
- [9. Tests](#9-tests)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.11+ (3.12 tested) | backend |
| Node.js | 20+ (22 tested) | frontend |
| Docker Desktop | optional | one-command deployment |

The first run downloads the `all-MiniLM-L6-v2` embedding model (~90 MB) from Hugging Face. After that it loads from the local cache.

## 2. Install and run locally

```bash
cd remotehunt

# Backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
# Generate an encryption key for OAuth tokens and paste it into FERNET_KEY in .env:
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

cd backend
../.venv/bin/python -m uvicorn app.main:app --port 8765     # API on http://localhost:8765

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                                 # UI on http://localhost:5173
```

The backend listens on **port 8765**, not 8000, so it doesn't clash with other local services. The Vite dev server proxies `/api` to it.

**First steps in the UI**

1. **Resume → Upload** your PDF or DOCX. You get the ATS score, parsed JSON, suggestions and skill gap. All jobs are rescored in the background.
2. **Dashboard → Run search now**, or wait: the scheduler runs a search 2 minutes after start and then every 6 hours.
3. **Settings & Gmail → Connect Gmail** once OAuth is set up (section 3).
4. Edit `config/profile.yaml` if your preferences change. It is re-read on every run.

Data lives in `./data` (SQLite database, uploaded resume versions, and a fallback encryption key). Back that folder up.

## 3. Google Cloud OAuth for Gmail

RemoteHunt uses exactly two scopes:

| Scope | Why |
|---|---|
| `gmail.modify` | read alert and recruiter emails, apply `RemoteHunt/*` labels, create **drafts** |
| `gmail.send` | send the daily digest **to your own address only** |

In code, the send path is hard-wired to the connected account. It refuses to send if that account differs from `GMAIL_ADDRESS` in `.env`. There is no code path that sends to a recruiter: replies and follow-ups are only ever created as drafts.

### Step by step

1. Open <https://console.cloud.google.com/> and **create a project** (e.g. `RemoteHunt`).
2. **APIs & Services → Library →** search **Gmail API → Enable**.
3. **APIs & Services → OAuth consent screen** (called *Google Auth Platform → Branding / Audience / Data access* in the newer console):
   - User type: **External**.
   - App name `RemoteHunt`, user support email and developer contact: your Gmail.
   - **Data access / Scopes → Add or remove scopes →** add `https://www.googleapis.com/auth/gmail.modify` and `https://www.googleapis.com/auth/gmail.send`.
   - **Audience / Test users:** add your Gmail address.
4. **Publish the app to Production.** Go to **Audience** (or **OAuth consent screen**), click **Publish app**, then confirm.
   > **Why this matters:** while an app is in *Testing*, Google expires its refresh tokens after **7 days**. Gmail would then stop working every week until you reconnect. In *Production* the token keeps working.
   >
   > Because these are restricted Gmail scopes and the app isn't verified, Google shows a **"Google hasn't verified this app"** screen when you connect. For your own personal app that's expected: click **Advanced → Go to RemoteHunt (unsafe)**. Verification is only needed if you publish the app for other people. Unverified apps are capped at 100 users, which doesn't matter here.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Authorized redirect URI: `http://localhost:8765/api/gmail/auth/callback` (the same URI works for local dev and Docker).
6. Copy the **Client ID** and **Client secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
   ```
   Alternatively, download the JSON and set `GOOGLE_CLIENT_SECRETS_FILE=/absolute/path/client_secret.json`.
7. Restart the backend, then open **Settings & Gmail → Connect Gmail** and sign in with the address in `GMAIL_ADDRESS`. If you sign in with a different account, the connection is refused.

The access and refresh tokens are stored in the database **encrypted with Fernet** (`FERNET_KEY`). If you lose or change `FERNET_KEY`, just reconnect Gmail. **Disconnect** revokes the token with Google and deletes it locally.

### What Gmail is used for

| Feature | When | Gmail action |
|---|---|---|
| Job-alert ingestion (LinkedIn, Naukri, Indeed, foundit, Instahyre, Wellfound, Internshala, Cutshort, Glassdoor, Hirist) | every search (6h) | read alert emails from the last 3 days, label `RemoteHunt/Job Alert` |
| Recruiter labelling | every search (6h) or **Sync & label now** | label `RemoteHunt/Recruiter` plus `Interview`, `Rejection` or `Application Update` |
| Reply drafts | only when you click **Draft reply** | `drafts.create` in the same thread. You review and send it yourself. |
| 7-day follow-ups | daily | reminders for applications 7+ days old and for threads where you wrote last and got no reply; **Draft follow-up** creates a draft |
| Daily digest | 08:00 IST | one email **to yourself** |

## 4. API keys

All of these are optional. A source without its key shows **Needs setup** on the Sources page and is skipped.

| Service | Where to get it | `.env` variable(s) | Notes |
|---|---|---|---|
| **Groq** (LLM) | <https://console.groq.com/keys> → *Create API key* | `GROQ_API_KEY` (optional `GROQ_MODEL`, default `openai/gpt-oss-120b`) | Powers line-by-line rewrites, tailoring, cover letters, profile text and reply drafts. Without it, everything falls back to rules and templates. Contact details are stripped before any text is sent. The app caps calls at `LLM_DAILY_CAP` per day and spaces them ≥ 2.5 s apart. |
| **Adzuna** | <https://developer.adzuna.com/> → register → *Dashboard* shows `app_id` and `app_key` | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | India market (`country: in`). Capped at 24 calls/day (3 queries × 4 runs), far below Adzuna's free limits. |
| **Jooble** | <https://jooble.org/api/about> → request a key by email form | `JOOBLE_API_KEY` | The key has a **500-request lifetime budget**, so the source runs **weekly** with 3 queries. The count is persisted in the DB and the source stops at 500. |
| **Careerjet** | <https://www.careerjet.com/partners/> → sign up for a partner/affiliate ID | `CAREERJET_AFFID` | **Disabled by default.** Enable with `careerjet.enabled: true` in `config/sources.yaml`. |

These need **no key**: Remotive, Remote OK, We Work Remotely (RSS), Himalayas, Jobicy, Arbeitnow, Working Nomads, The Muse (public API; remote plus Indian cities, good for hybrid roles), Hasjob (Indian startups, Atom feed), 4dayweek.io, Real Work From Anywhere and Jobspresso (RSS), HN "Who is hiring" and YC job posts (Algolia API), and the Greenhouse, Lever, Ashby, Workable and SmartRecruiters public job-board APIs.

**Hybrid jobs:** a hybrid or on-site job is marked eligible only if it's in one of `onsite_ok_locations` in `config/profile.yaml` (Delhi NCR by default). A job in another Indian city with no stated work mode shows as "Check region". Add cities to that list if you'd relocate. Use **Jobs → Work type** to filter to remote or hybrid only.

**More alerts, for free:** create job alerts on Internshala, Cutshort, Glassdoor, Hirist, LinkedIn, Naukri, Indeed, foundit, Instahyre and Wellfound, sent to your connected Gmail. RemoteHunt parses them automatically every 6 hours. This is how sites without a public API are covered without scraping.

Remote OK, Jobicy and Himalayas ask that jobs link back to them. RemoteHunt shows the source on every job and "Open posting" goes to the original URL.

## 5. Run with Docker

```bash
cd remotehunt
cp .env.example .env         # fill in FERNET_KEY and any keys (section 4)
docker compose up -d --build
```

- UI: <http://localhost:8080>. API: <http://localhost:8765>.
- In the Google Cloud client, keep the redirect URI `http://localhost:8765/api/gmail/auth/callback`. Compose already sets `FRONTEND_URL=http://localhost:8080`, so after sign-in you land back in the Docker UI.
- Volumes: `./data` (DB, resumes, key), `./config` (read-only YAML), `hf-cache` (the embedding model).
- Logs: `docker compose logs -f backend`
- Update after code changes: `docker compose up -d --build`

**Postgres instead of SQLite**

```bash
# in .env
DATABASE_URL=postgresql+psycopg://remotehunt:remotehunt@postgres:5432/remotehunt
docker compose --profile postgres up -d --build
```

Tables are created automatically on start. The models use only portable types, so the same schema runs on both databases.

## 6. Configuration files

| File | What it controls |
|---|---|
| `config/profile.yaml` | Target roles, time zone and tolerance, paid-only filter, on-site cities you'd accept, search queries, match thresholds (`tailor_min_score` 70, digest settings), Gmail digest address, follow-up days |
| `config/sources.yaml` | Every source plugin: `enabled`, `limits`, `params`, and `active_health` (whether a health check may spend a real API call) |
| `config/target_companies.yaml` | Company boards for Greenhouse, Lever, Ashby, Workable and SmartRecruiters. Every token was checked against its API on 2026-09-28. A wrong token shows up as a failure for that company on the Sources page and is skipped. |

**Adding a source plugin:** subclass `Source` in `backend/app/sources/`, implement `fetch(queries) -> list[RawJob]` (and optionally `ping()`), register the class in `sources/registry.py → TYPES`, and add a block to `sources.yaml`. The shared `BudgetedClient` enforces limits for you. Any exception in a source is caught, logged and recorded as that source's health; it never stops the run.

## 7. Schedules and rate limits

All times are **Asia/Kolkata (IST)**.

| Job | Schedule |
|---|---|
| Search: health checks → all due sources → Gmail sync | every 6 hours (first run 2 min after start) |
| Daily digest | 08:00 every day |
| Weekly resume check-in: re-scores ATS, skill priorities, activity, nudges | Monday 09:00 |
| Monthly market-trend report: top and rising skills, employers, salary medians | 1st of the month, 09:30 |

Every outbound call is recorded in the `api_calls` table and checked **before** it is made:

| Source | Limit enforced |
|---|---|
| Remotive | **≤ 4 calls / rolling 24h** (one call per run) |
| Remote OK, Working Nomads | ≤ 4 / day |
| Jobicy | ≤ 12 / day, 5 s spacing (asks for ≤ 1 poll/hour) |
| Himalayas, WWR, Arbeitnow | ≤ 16–24 / day, 3 s spacing |
| HN Who's Hiring | once a day |
| Greenhouse, Lever, Ashby, Workable, SmartRecruiters | once a day per company, 1.5–2 s spacing |
| Adzuna | ≤ 24 / day |
| Jooble | weekly, ≤ 3 / week, **≤ 500 lifetime** |
| Careerjet | disabled; ≤ 6 / day if enabled |
| Groq | `LLM_DAILY_CAP` / day, ≥ 2.5 s apart |

An HTTP 429 puts the source into back-off (honouring `Retry-After`, minimum 60 s). Health checks on tightly budgeted APIs never spend a call: their health comes from the most recent run. **Run search now** (and `force` from the API) skips the "min hours between runs" wait but never exceeds a budget.

## 8. Privacy and safety rules

- **No scraping.** Only official APIs, RSS, and your own Gmail via the Gmail API. Alert emails are parsed from your inbox; job pages are never fetched.
- **No auto-apply.** You apply via the "Open posting" link. The tracker only records what you did.
- **Nothing sent without approval.** Tailored documents start as **drafts**. Export (PDF/DOCX) is blocked until you approve, and editing puts a document back into draft.
- **Never emails recruiters.** Reply and follow-up text only ever becomes a Gmail draft. The only send is the digest to your own address.
- **Truthfulness guardrail.** AI output that mentions a skill, number, years of experience, seniority title, degree or certification that isn't on your resume is rejected. Rejected AI text falls back to your own words or a template, and the rejected claims are shown to you.
- **No personal data in logs.** Modules log counts and types only. A redaction filter on every log handler also masks emails, phone numbers, API keys and OAuth codes, and HTTP client URL logging is silenced. Exceptions are logged by type, not message.
- OAuth tokens are **Fernet-encrypted** at rest. `.env`, `data/` and resume files are git-ignored.

## 9. Tests

```bash
cd backend
../.venv/bin/python -m pytest -q
```

49 tests cover the resume parser (DOCX/PDF round-trips, sections, wrapped bullets, ATS scoring), the matcher (ranking with both a deterministic embedder and the real MiniLM model, reasons, missing skills, seniority, years parsing, non-technical roles) and the scam detector (fees, negation, messaging apps, personal email, crypto/cheque, thin posts). They also cover region eligibility, dedupe, the guardrail, budgets, HN parsing, alert-email parsing and email classification. Tests use a temporary database and never call the network or the LLM, except the one MiniLM test, which downloads the model if it isn't cached and skips if it can't.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Port 8765 or 8080 already in use | Change the host port in `docker-compose.yml`, or `--port` for uvicorn. For local dev also set `VITE_BACKEND_URL`. Update the OAuth redirect URI to match. |
| Gmail says *access blocked* or *redirect_uri_mismatch* | The redirect URI in Google Cloud must exactly equal `OAUTH_REDIRECT_URI`. |
| Gmail works for a week, then stops | The consent screen is still in *Testing*: publish it to Production (section 3, step 4), then reconnect. |
| "Stored token could not be decrypted" | `FERNET_KEY` changed. Reconnect Gmail. |
| A source shows **Degraded** | Open **Sources → Runs** for the error. For ATS sources, the per-company status shows which token failed. |
| **Budget used** on a source | Expected: it resumes when the rolling window frees up (Jooble: once the 500 lifetime calls are used, the source stays off). |
| Himalayas search returns 404 | Their search endpoint is sometimes served as a cached 404. The connector automatically falls back to the documented cursor-paginated feed. |
| Scores look off after changing `profile.yaml` | **Jobs → Rescore all** (takes ~2 min for a few thousand jobs). Uploading a resume version also rescores everything. |
