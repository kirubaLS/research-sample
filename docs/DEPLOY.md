# Deploying Yaadhum

Two web services and one database. `render.yaml` at the repo root defines all three, so
Render can build the whole thing from a Blueprint.

---

## 1. The stack, and what it can and cannot promise

**Render** for both services, **Neon** for Postgres. `render.yaml` has no `databases:`
block — Neon is wired in as an external database through two secrets.

**Neither Render nor Neon has an India region.** Render offers Oregon, Ohio, Virginia,
Frankfurt and Singapore; Neon's nearest is Singapore (`ap-southeast-1`). Put both in
Singapore so the API and database are co-located — a cross-region hop on every query is
the difference between a snappy dashboard and a sluggish one.

That is the right stack for **testing**. It cannot give Indian data residency, and student
answer scripts contain children's handwriting, so:

| | Fine on Render + Neon | Move the data tier first |
|---|---|---|
| Synthetic and seeded data | ✅ | |
| Your own sample scripts | ✅ | |
| A school's real answer scripts | | ✅ `ap-south-1` — RDS, or Postgres on a Mumbai VM |
| Anything where residency was promised | | ✅ |

Moving later is a connection-string change plus a dump/restore, not a rewrite. But do not
tell a school data stays in India while running on this stack.

---

## 2. Neon: the two things that will bite

### 2.1 Use the pooled endpoint for the app, the direct one for migrations

Neon gives you two connection strings. The pooled one has **`-pooler`** in the hostname and
runs PgBouncer in transaction-pooling mode.

```
# pooled — for the running app (many short-lived connections)
postgresql://user:pw@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/yaadhum?sslmode=require

# direct — for Alembic
postgresql://user:pw@ep-xxx.ap-southeast-1.aws.neon.tech/yaadhum?sslmode=require
```

Set them as:

| Env var | Which endpoint |
|---|---|
| `YAADHUM_DATABASE_URL` | **pooled** |
| `YAADHUM_MIGRATION_DATABASE_URL` | **direct** |

Migrations need the direct endpoint because the advisory locks and session state Alembic
relies on do not survive transaction pooling. `migrations/env.py` reads
`settings.migration_url`, which prefers the direct URL and falls back to the pooled one, so
a single-URL setup still works — it is just riskier.

### 2.2 Prepared statements must be off on the pooled endpoint

psycopg keeps server-side prepared statements. Under transaction pooling a later
transaction lands on a different backend that has never seen them, and you get
`prepared statement "_pg3_0" already exists` — intermittently, under load, which is the
worst way to find out.

`app/db.py` detects `-pooler` in the URL and sets `prepare_threshold=None`. Nothing to
configure; just do not strip `-pooler` out of the hostname thinking it is cosmetic.

### 2.3 Auto-suspend

Neon's free tier suspends the compute after a few minutes idle, and the next query wakes
it. `pool_pre_ping=True` absorbs that, so it shows up as one slow request rather than an
error. Combined with Render's free tier sleeping, the first request after a quiet spell can
take a while — use `starter` on Render for anything a teacher will touch.

`render.yaml` sets a small pool (3 + 2 overflow) to stay well inside Neon's connection
ceiling.

---

## 3. Deploy

1. Push the branch and open **Render → New → Blueprint**, pointing at this repository.
2. Render reads `render.yaml` and proposes `yaadhum-api` and `yaadhum-web`. There is no
   database service — Neon is external.
3. Fill in the secrets it marks as required (they are `sync: false`, so they are never in
   the repo):
   - `YAADHUM_DATABASE_URL` — the Neon **pooled** string
   - `YAADHUM_MIGRATION_DATABASE_URL` — the Neon **direct** string
   - `ANTHROPIC_API_KEY`
   - `YAADHUM_S3_BUCKET`, `YAADHUM_S3_ENDPOINT_URL`, `YAADHUM_S3_ACCESS_KEY_ID`,
     `YAADHUM_S3_SECRET_ACCESS_KEY`
4. Deploy. The API's pre-deploy step runs `alembic upgrade head` before the new instance
   takes traffic.
5. Once the URLs are assigned, fix the two cross-references and redeploy:
   - `yaadhum-api` → `YAADHUM_CORS_ORIGINS` = the web service's URL
   - `yaadhum-web` → `NEXT_PUBLIC_API_BASE` = the API's URL
6. Seed the first school:
   The deploy runs `alembic upgrade head`, which creates the schema and nothing else.
   A freshly deployed database has **no school in it**, so nobody can sign in and the
   student class list is empty until you provision one. Open the API service's **Shell**
   tab in the Render dashboard (or `render shell yaadhum-api` with the CLI) and run:

   ```bash
   cd backend
   python -m scripts.create_school "Bharath International Sr. Sec. School" \
       --state "Tamil Nadu" --sections 10-A 10-B
   ```

   It prints the school's API key -- the principal's only credential -- and one
   `/t/<class-code>` link per section. It is safe to re-run: an existing school keeps its
   key and only missing sections are added.

   Do **not** run `python -m scripts.seed` against a school's live database. That is the
   laptop script; it invents forty students so the dashboard has something to show.

   No students are created here. A student enrols themselves the first time they open the
   class link and fill in the form.

   **Retrieving the key later**, from the same shell:

   ```bash
   cd backend
   python -m scripts.admin_key                        # every school and its key
   python -m scripts.admin_key --rotate <school-id>   # new key if one leaks
   ```

   **Or do it from the browser instead.** Set `YAADHUM_PLATFORM_ADMIN_KEY` on the API
   service to a long random string (`python -c "import secrets;print(secrets.token_urlsafe(32))"`),
   redeploy, then open `/platform` on the web service and sign in with it. That console
   creates schools, adds classes, and issues or rotates a principal's key -- the same
   things the two scripts do, without a shell.

   The console's key is deliberately a **different secret** from any school's API key.
   A principal holds one key for one school; if that key could also create schools or read
   another school's key, one leaked key would compromise every school on the deployment.
   Leaving `YAADHUM_PLATFORM_ADMIN_KEY` unset turns the console off entirely rather than
   falling back to something weaker.

   A key is shown **once**, when it is created or rotated. No route reads one back, so if
   a principal loses theirs the remedy is *Issue a new principal key*, which takes effect
   on the next request and leaves class links untouched.

   If your plan has no Shell tab, you can read the same value straight from Neon's SQL
   editor -- `select id, name, api_key from school;` -- but prefer the shell: rotation
   through the script keeps the key in the format the app validates.

---

## 4. The five things that bite on split hosting

**CORS.** The frontend is a different origin, so without it every request fails at the
browser. Configured in `app/main.py` from `YAADHUM_CORS_ORIGINS`, and deliberately not
`*` — `/t/{class_code}/start` takes no API key, so a wildcard would let any site drive it.

**`NEXT_PUBLIC_API_BASE` is a build-time variable.** Next inlines `NEXT_PUBLIC_*` into the
bundle at build time. Changing it in the dashboard and restarting does nothing; you have to
trigger a rebuild.

**The health check path.** `render.yaml` points at `/healthz`, which touches nothing.
`/health` is the readiness probe and does hit the database — if the platform polls that
one, a brief database blip restarts a perfectly healthy process.

**The database URL scheme.** Render hands out `postgres://`, which SQLAlchemy 2 refuses to
load. `app/config.normalise_database_url` rewrites it to `postgresql+psycopg://`, so the
platform's own connection string can be pasted in unchanged.

**The frontend is a Web Service, not a Static Site.** `/t/[classCode]` and its test page are
server-rendered on demand — a class code is a runtime value, so it cannot be pre-rendered.
Creating the frontend as a Static Site fails with `Publish directory dist does not exist!`
*after* a successful build, which reads as a build problem but is a service-type problem.

**Free instances sleep.** A sleeping API means the first request after idle takes ~30s —
which, mid-scan with a teacher holding a phone over a script, reads as broken. `starter` is
the floor for anything a school touches.

---

## 5. Not on Render

**Object storage.** Render has no S3 equivalent, and its persistent disks bind to a single
instance. Use Cloudflare R2 (cheap, no egress fees, set a jurisdictional restriction) or
AWS S3 in `ap-south-1`. Set `YAADHUM_STORAGE_BACKEND=s3` and install the extra:
`pip install -e ".[storage]"`.

**Background workers.** Page extraction and report builds should not run in the web
process. Add a Render Background Worker plus a Key Value (Redis) instance when the
extraction pipeline lands; `arq` is already the intended runner.

---

## 6. Alternatives worth knowing

| Option | Why you might |
|---|---|
| **Render (both services)** | Simplest. One blueprint, managed Postgres, pre-deploy migrations. No India region. |
| **Vercel (web) + Render (API)** | Better Next.js DX and edge caching; the API and data still need a home. |
| **Render + Neon (this setup)** | Fastest to stand up, generous free tiers, branchable database. No Indian residency. |
| **AWS `ap-south-1` end to end** | The only way to promise Indian residency for everything. ECS/App Runner + RDS + S3. More setup, and the answer once schools start asking. |
| **Single VM in Mumbai** | One `docker compose up` on a Hetzner/E2E/AWS box. Cheapest path to true residency for a pilot; you own the ops. |

For testing: **Render Singapore + Neon Singapore**, exactly as `render.yaml` is set. Before
a school's real scripts go in, move the data tier to `ap-south-1` — a connection string and
a dump/restore, not a rewrite.

---

## 7. Verifying a live deploy

```bash
API=https://yaadhum-api.onrender.com

curl -s $API/healthz                      # {"status":"ok"} — no database touched
curl -s $API/health | jq                  # database: up, environment: production

# CORS is configured for the web origin and nothing else
curl -si -X OPTIONS $API/health \
  -H "Origin: https://yaadhum-web.onrender.com" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin

curl -si -X OPTIONS $API/health \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin || \
  echo "correctly refused"
```

Then seed the first school from the Render shell and open `/t/<class-code>`.
