# Running Yaadhum free on Render

For testing. Costs nothing, and three things behave differently from a paid deployment.
All three are stated here rather than discovered.

## What it costs you

**It sleeps.** Both services stop after 15 minutes idle and the next request waits about
50 seconds for a cold start. Fine while you are building. Open the page a minute before
you show it to anybody.

**Scanned page images do not survive a restart.** A free instance has no persistent disk.
The marks, the reports, the question papers and the roster are all in Postgres and are
unaffected — it is the page *images* that go, and a request for one afterwards answers
`410` with a sentence saying so rather than failing. Fix it by pointing the app at any
S3-compatible bucket; Cloudflare R2 has a free tier and
`YAADHUM_S3_ENDPOINT_URL` exists for exactly that.

**Use Neon for Postgres, not Render's free database.** A free Render Postgres is deleted
30 days after it is created, and the thirtieth day is not a day anybody remembers. Neon's
free project has no such clock.

## Setting it up

1. **Neon** — create a free project in Singapore (`ap-southeast-1`). Copy both connection
   strings: the **pooled** one (hostname contains `-pooler`) and the **direct** one.
2. **Render** — New → Blueprint → point at this repo. It reads `render.yaml`.
3. Fill in the secrets it asks for, in the dashboard:

   | Variable | Value |
   |---|---|
   | `YAADHUM_DATABASE_URL` | Neon **pooled**, as `postgresql+psycopg://…` |
   | `YAADHUM_MIGRATION_DATABASE_URL` | Neon **direct**. Alembic needs it: the locks a migration takes do not survive transaction pooling |
   | `ANTHROPIC_API_KEY` | for the classifier and the family proposer |
   | `YAADHUM_JINA_API_KEY` | for embeddings; without it three of the four familiarity levels collapse |
   | `YAADHUM_PLATFORM_ADMIN_KEY` | leave unset to keep the operator console off |

4. Wait for the first deploy. The image migrates the database and then serves, so there is
   nothing to run by hand.

5. Create the first school at `/platform` with the operator key, then sign in at `/admin`
   with the school key it gives you once.

## Checking it actually works

The build itself proves text recognition runs — the image renders a page, photographs it
and reads it back, and fails the build if nothing comes out. After that:

- `/healthz` answers 200.
- `/admin` asks for a key.
- Read a question paper, enter marks from a spreadsheet, issue a report.
- Upload an answer script, then wait for a sleep and load it again: the page should say
  `410` with an explanation, not break. That is the free tier working as described.

## Moving off

`plan: free` → `plan: starter` on both services removes the sleeping and gives the API a
disk. Everything else is unchanged. Production is `infra/aws` or `infra/ec2`; both run the
same image, so it is a deploy target rather than a rewrite.
