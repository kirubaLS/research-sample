# Running Yaadhum free on Render

For testing. Costs nothing, and three things behave differently from a paid deployment.
All three are stated here rather than discovered.

## What it costs you

**It sleeps.** Both services stop after 15 minutes idle and the next request waits about
50 seconds for a cold start. Fine while you are building. Open the page a minute before
you show it to anybody.

**Scanned pages go in Postgres, not in a bucket.** A free instance has no persistent disk,
and this deployment has no object store, so Neon is the only thing that survives a
restart — `YAADHUM_STORAGE_BACKEND=database` puts the page images in the row beside the
marks and they last exactly as long.

The cost is space. Neon's free project gives 0.5 GB, which the marks alone would never
approach and photographs will: roughly **forty scripts of eight pages fills a third of it**.
Watch the storage figure on the Neon dashboard and switch to `s3` before it is a problem,
not after. On AWS it is `s3` from the start, which is why the setting exists.

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
- Upload an answer script, wait for the service to sleep, then load the page again. It
  should still be there: the pages are in Neon, not on the instance's disk.

## Moving off

`plan: free` → `plan: starter` on both services removes the sleeping and gives the API a
disk. Everything else is unchanged. Production is `infra/aws` or `infra/ec2`; both run the
same image, so it is a deploy target rather than a rewrite.
