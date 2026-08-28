# Deploying Yaadhum

Two web services and one database. `render.yaml` at the repo root defines all three, so
Render can build the whole thing from a Blueprint.

---

## 1. Decide the data-residency question first

**Render has no India region.** Available regions are Oregon, Ohio, Virginia, Frankfurt
and Singapore. Singapore is the closest to Tamil Nadu and is what `render.yaml` sets.

That matters because student answer scripts contain children's handwriting, and where that
data *rests* is a DPDP Act question rather than a latency question. Two workable postures:

| | Compute | Database + object store | When |
|---|---|---|---|
| **Pilot** | Render, Singapore | Render Postgres, Singapore | One school, disclosed in the school agreement |
| **Production** | Render, Singapore | **External, `ap-south-1`** — RDS / Neon / Supabase, plus an ap-south-1 bucket | Before you sign a paying school |

Render services connect to an external database with no change to `render.yaml` — you
replace the `fromDatabase` block with a `sync: false` secret and paste the external URL.

> Do not tell a school that data stays in India while running the managed database in
> Singapore. If residency is promised, move the data tier first.

---

## 2. Deploy

1. Push the branch and open **Render → New → Blueprint**, pointing at this repository.
2. Render reads `render.yaml` and proposes `yaadhum-api`, `yaadhum-web` and `yaadhum-db`.
3. Fill in the secrets it marks as required (they are `sync: false`, so they are never in
   the repo):
   - `ANTHROPIC_API_KEY`
   - `YAADHUM_S3_BUCKET`, `YAADHUM_S3_ENDPOINT_URL`, `YAADHUM_S3_ACCESS_KEY_ID`,
     `YAADHUM_S3_SECRET_ACCESS_KEY`
4. Deploy. The API's pre-deploy step runs `alembic upgrade head` before the new instance
   takes traffic.
5. Once the URLs are assigned, fix the two cross-references and redeploy:
   - `yaadhum-api` → `YAADHUM_CORS_ORIGINS` = the web service's URL
   - `yaadhum-web` → `NEXT_PUBLIC_API_BASE` = the API's URL
6. Seed the first school:
   ```bash
   render shell yaadhum-api     # or the dashboard shell
   python -m scripts.seed
   ```
   It prints the API key and the class code. `/t/<class-code>` is the student link.

---

## 3. The five things that bite on split hosting

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

**Free instances sleep.** A sleeping API means the first request after idle takes ~30s —
which, mid-scan with a teacher holding a phone over a script, reads as broken. `starter` is
the floor for anything a school touches.

---

## 4. Not on Render

**Object storage.** Render has no S3 equivalent, and its persistent disks bind to a single
instance. Use Cloudflare R2 (cheap, no egress fees, set a jurisdictional restriction) or
AWS S3 in `ap-south-1`. Set `YAADHUM_STORAGE_BACKEND=s3` and install the extra:
`pip install -e ".[storage]"`.

**Background workers.** Page extraction and report builds should not run in the web
process. Add a Render Background Worker plus a Key Value (Redis) instance when the
extraction pipeline lands; `arq` is already the intended runner.

---

## 5. Alternatives worth knowing

| Option | Why you might |
|---|---|
| **Render (both services)** | Simplest. One blueprint, managed Postgres, pre-deploy migrations. No India region. |
| **Vercel (web) + Render (API)** | Better Next.js DX and edge caching; the API and data still need a home. |
| **AWS `ap-south-1` end to end** | The only way to promise Indian residency for everything. ECS/App Runner + RDS + S3. More setup, and the answer once schools start asking. |
| **Single VM in Mumbai** | One `docker compose up` on a Hetzner/E2E/AWS box. Cheapest path to true residency for a pilot; you own the ops. |

For the pilot: **Render Singapore, with the data tier pointed at `ap-south-1`.** That gets
you deployed this week without making a residency claim you would have to walk back.
