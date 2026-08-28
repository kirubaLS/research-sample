# Setup

Every command below was run from a clean clone before it was written down.

Two ways to run it:

* **Local** — SQLite, no accounts needed. Fifteen minutes. Start here.
* **Neon + Render** — a real Postgres and a public URL. Section 4.

---

## 0. Prerequisites

| | Version | Check |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| Node | 20+ | `node --version` |
| git | any | `git --version` |

---

## 1. Backend, locally

```bash
git clone <your-repo-url> yaadhum && cd yaadhum/backend

python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Create `backend/.env`. SQLite needs nothing else running:

```bash
cat > .env <<'ENV'
YAADHUM_ENVIRONMENT=development
YAADHUM_DATABASE_URL=sqlite+pysqlite:///./yaadhum.db
YAADHUM_CORS_ORIGINS=http://localhost:3000
ENV
```

Create the schema, then seed a demo school:

```bash
alembic upgrade head
python -m scripts.seed
```

`seed` prints three things you need next — keep the terminal open:

```
school     : Bharath International Sr. Sec. School
API key    : zozx6r94sEf1KWs7fRdXTNJNYXKEteuW     <- for the dashboard
class code : 6b3c86ba-6a48-4601-a6cc-0868ae625009 <- the student link
assessment : 9892e1a1-43f4-43da-a279-f9ec3062bc12
```

**Lost the key?** There are no admin accounts and no passwords — one API key per school,
held by the principal and sent as `X-API-Key`. To print it again at any time:

```bash
python -m scripts.admin_key                        # every school and its key
python -m scripts.admin_key --rotate <school-id>   # issue a new key if one leaks
```

On Render, run the same command from the API service's **Shell** tab.

Run it:

```bash
uvicorn app.main:app --reload --port 8000
```

Check it in another terminal:

```bash
curl -s localhost:8000/healthz     # {"status":"ok"} — liveness, touches nothing
curl -s localhost:8000/health      # readiness: database up
open http://localhost:8000/docs    # the full API
```

Run the tests once so you know the machine is sane — **89 should pass**:

```bash
pytest -q
```

---

## 2. Frontend, locally

In a second terminal:

```bash
cd yaadhum/frontend
npm install
cp .env.local.example .env.local          # already points at localhost:8000
npm run dev
```

Open **http://localhost:3000**.

> `NEXT_PUBLIC_API_BASE` is inlined at **build** time. In dev the reload picks it up; in
> production, changing it needs a rebuild, not a restart.

---

## 3. Walk the app

**As a student** — open `http://localhost:3000/` and follow *Take the interest test*, which
lists the classes so a student can tap their own. The direct link is
`http://localhost:3000/t/<class-code>` using the class code `seed` printed; the dashboard
shows the same link with a Copy button, next to each class.

1. Fill the form. Pick **தமிழ்** to see the Tamil item text.
2. Six screens, six items each. Answers save on every tap.
3. It ends at *Thank you* — no score, no code, no stream. That boundary is a database rule,
   not a hidden button.

**As the principal** — `http://localhost:3000/admin`.

The dashboard reads the API with the `X-API-Key` header. To see the profile the student
just produced:

```bash
API_KEY=<the key seed printed>

# find the student id
curl -s localhost:8000/reports/interest/<student-id> -H "X-API-Key: $API_KEY" | jq
```

You should see the Holland code, the six scale scores with credible intervals, the stream
fit, and `recommendation_withheld` — which is `true` when the profile came out flat, with
the reason attached.

**The marks engine** — the interesting call is the constraint solver. This is the worked
example from the design docs: the model prefers 3 on Q19, the cover total says 5.

```bash
ASSESSMENT=<the assessment id seed printed>

curl -s -X POST localhost:8000/assessments/$ASSESSMENT/reconcile \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "student_roll": "001",
    "distributions": {
      "B/21//": {"2": 0.94, "1": 0.05, "0": 0.01},
      "B/23//": {"2": 0.52, "1": 0.44, "0": 0.04},
      "B/24//": {"2": 0.88, "1": 0.10, "0": 0.02}
    },
    "grand_total": 5.0
  }' | jq
```

The naive read sums to 6. The solver returns an assignment summing to exactly 5, having
corrected the ambiguous item — because the arithmetic is ground truth.

---

## 4. Neon + Render

### 4.1 Neon

1. **neon.tech** → new project. Region **Singapore (`ap-southeast-1`)** — the closest to
   Tamil Nadu that Neon offers, and it matches where Render will run.
2. On the dashboard, copy **both** connection strings. They differ by one thing:

   | | hostname | use for |
   |---|---|---|
   | **Pooled** | contains `-pooler` | the running app |
   | **Direct** | no `-pooler` | Alembic migrations |

   Toggle "Connection pooling" on the dashboard to switch between them.

3. Migrations need the **direct** string. PgBouncer runs the pooled endpoint in
   transaction-pooling mode, and the locks Alembic relies on do not survive it.

To point your **local** backend at Neon instead of SQLite, put both in `backend/.env`:

```bash
YAADHUM_DATABASE_URL=postgresql://user:pw@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/yaadhum?sslmode=require
YAADHUM_MIGRATION_DATABASE_URL=postgresql://user:pw@ep-xxx.ap-southeast-1.aws.neon.tech/yaadhum?sslmode=require
```

Then `alembic upgrade head && python -m scripts.seed` again. The `postgres://` scheme is
normalised automatically, so paste Neon's string exactly as given.

### 4.2 Render

1. **Render → New → Blueprint**, point it at the repo. It reads `render.yaml` and proposes
   `yaadhum-api` and `yaadhum-web`. There is no database service — Neon is external.
2. Fill in the secrets it marks required:

   | Key | Value |
   |---|---|
   | `YAADHUM_DATABASE_URL` | Neon **pooled** |
   | `YAADHUM_MIGRATION_DATABASE_URL` | Neon **direct** |
   | `ANTHROPIC_API_KEY` | your key |
   | `YAADHUM_S3_*` | leave blank until the scanner needs storage |

3. Deploy. The pre-deploy step runs `alembic upgrade head` before the new instance takes
   traffic.
4. Once Render assigns the URLs, fix the two cross-references:

   | Service | Key | Value |
   |---|---|---|
   | `yaadhum-api` | `YAADHUM_CORS_ORIGINS` | `https://yaadhum-web.onrender.com` |
   | `yaadhum-web` | `NEXT_PUBLIC_API_BASE` | `https://yaadhum-api.onrender.com` |

   **Redeploy the web service** after changing its variable — a restart is not enough.
5. Seed the first school from the Render shell on `yaadhum-api`:

   ```bash
   python -m scripts.seed
   ```

### 4.3 Verify the live deploy

```bash
API=https://yaadhum-api.onrender.com

curl -s $API/healthz
curl -s $API/health | jq        # environment: production, database: up

# CORS must allow your web origin and refuse everything else
curl -si -X OPTIONS $API/health -H "Origin: https://yaadhum-web.onrender.com" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
curl -si -X OPTIONS $API/health -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin \
  || echo "correctly refused"
```

> Neither Render nor Neon has an India region. Fine for testing with synthetic data. Before
> a school's real answer scripts go in, move the data tier to `ap-south-1` — see
> [DEPLOY.md](DEPLOY.md).

---

## 5. When it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `Publish directory dist does not exist!` after a successful `next build` | The frontend was created as a Render **Static Site**. Two routes are server-rendered on demand, so there is no static output directory | Delete it and recreate as a **Web Service** (Node), or deploy via the Blueprint, which sets `type: web`. Render cannot convert a service type in place |
| `npm audit`: high severity in `postcss` | Transitive dependency of Next | Already pinned via an `overrides` entry. Do **not** run `npm audit fix --force` — it installs Next 16, a major version jump |
| `Multiple top-level packages discovered in a flat-layout` | Old checkout — `pyproject.toml` must declare `packages = ["app"]` | Pull `main` |
| `SettingsError: error parsing value for field "cors_origins"` | Old checkout — list settings need `NoDecode` | Pull `main` |
| Browser console: *blocked by CORS policy* | `YAADHUM_CORS_ORIGINS` does not match the web origin exactly | Include the scheme, no trailing slash, then restart the API |
| Frontend calls `localhost:8000` in production | `NEXT_PUBLIC_API_BASE` is inlined at build time | Change it, then **rebuild** the web service |
| `Can't load plugin: sqlalchemy.dialects:postgres` | A raw `postgres://` URL reached SQLAlchemy | Already normalised in `app/config.py` — pull `main` |
| `prepared statement "_pg3_0" already exists`, intermittently | The pooled Neon endpoint with prepared statements on | `app/db.py` disables them when it sees `-pooler`; make sure you did not strip it from the hostname |
| Alembic hangs or errors on lock acquisition | Migrations running against the **pooled** endpoint | Set `YAADHUM_MIGRATION_DATABASE_URL` to the direct string |
| First request after idle takes ~30s | Render free tier sleeps and Neon free tier auto-suspends | Use Render `starter` for anything a teacher touches |
| `422` from an admin endpoint | The `X-API-Key` header is missing entirely | Add it; a *wrong* key returns 404 by design, never 403 |
| Camera does not open in the scanner | `getUserMedia` needs a secure context | `localhost` is fine; any other host needs HTTPS |

---

## 6. Everyday commands

```bash
make test      # 89 backend tests
make lint      # ruff
make api       # backend on :8000
make web       # frontend on :3000
make seed      # demo school, roster, taxonomy, assessment

# after changing a model
cd backend && alembic revision --autogenerate -m "what changed" && alembic upgrade head
```
