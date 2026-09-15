# Moving to AWS (ap-south-1, minimal cost)

One Lightsail VM running Docker Compose (Caddy + Next.js + FastAPI+Tesseract + Postgres),
one S3 bucket for scanned pages with a 30-day lifecycle rule. Everything for this lives in
this directory: `docker-compose.yml`, `Caddyfile`, `s3-lifecycle.json`,
`backup-postgres.sh`.

This is a **different** compose file from the one at the repo root -- that one is local
dev only (bare postgres/redis/minio, run against `next dev` / `uvicorn --reload` on your
own machine). Everything below runs from inside this `infra/` directory.

Do these in order. Steps marked **(console)** are click-through in the AWS Console
because they're one-time and low-value to script; steps marked **(CLI)** use the AWS CLI
(`aws configure` with an access key first).

## 1. AWS account and IAM

1. **(console)** Create the AWS account if you don't have one, sign in as root, enable
   MFA on it, then never use the root user again for day-to-day work.
2. **(console)** IAM → Users → create a user `yaadhum-admin` with **Console access** and
   **Programmatic access**. Attach `AdministratorAccess` for now — tighten later once the
   shape of what this app actually touches (S3, Lightsail, one bucket) is settled; a
   pilot's time is better spent shipping than hand-writing an IAM policy on day one.
3. **(CLI)** `aws configure` with that user's access key, region `ap-south-1`.

## 2. S3 bucket for scanned pages

```bash
aws s3api create-bucket \
  --bucket yaadhum-scans-prod \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

aws s3api put-bucket-encryption --bucket yaadhum-scans-prod \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block --bucket yaadhum-scans-prod \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# The 30-day auto-delete on scanned pages, and a housekeeping rule for abandoned uploads.
aws s3api put-bucket-lifecycle-configuration --bucket yaadhum-scans-prod \
  --lifecycle-configuration file://infra/s3-lifecycle.json
```

Bucket names are globally unique across all of AWS — if `yaadhum-scans-prod` is taken,
pick another and use it consistently below.

Create a scoped IAM user for the *app* to use (not your admin user) so the backend's own
credentials can only touch this one bucket:

```bash
aws iam create-user --user-name yaadhum-app
aws iam put-user-policy --user-name yaadhum-app --policy-name yaadhum-scans-rw \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:HeadObject"],
      "Resource": "arn:aws:s3:::yaadhum-scans-prod/*"
    }]
  }'
aws iam create-access-key --user-name yaadhum-app
```

Save that access key pair — it goes into `.env` as `YAADHUM_S3_ACCESS_KEY_ID` /
`YAADHUM_S3_SECRET_ACCESS_KEY` in step 5.

## 3. Lightsail VM

1. **(console)** Lightsail → Create instance → region **ap-south-1 (Mumbai)** → Linux/Unix
   → OS Only → **Ubuntu 24.04 LTS** → the $10/mo plan (2GB RAM/2 vCPU; the $5 plan's 1GB
   is tight once Postgres, Tesseract, Next.js and FastAPI are all running at once) →
   name it `yaadhum-prod` → Create.
2. **(console)** Networking tab on the instance → attach a **Static IP** (free while
   attached to a running instance) → Firewall: allow **80** and **443** (22 is open by
   default for the browser-based SSH). Remove the default HTTP rule's public health check
   noise if Lightsail added one.
3. **(console)** Point your domain's DNS: an A record for `app.yourdomain.in` and one for
   `api.yourdomain.in`, both at the static IP. (Keep DNS at your existing registrar —
   Route53 buys you nothing extra here.)
4. SSH in (the console's browser SSH button, or your own key) and install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
sudo apt-get install -y docker-compose-plugin
```

## 4. Get the code onto the VM

```bash
git clone https://github.com/<you>/<repo>.git /srv/yaadhum
cd /srv/yaadhum/infra
```

Everything from here on runs from inside `infra/`.

## 5. Configure `.env`

```bash
cp ../.env.example .env
nano .env
```

Set at minimum:
- `POSTGRES_PASSWORD` — anything long and random (`openssl rand -base64 24`); this is a
  compose-level variable, not one of the `YAADHUM_` app settings, and both
  `docker-compose.yml`'s `postgres` and `backend` services read it.
- `YAADHUM_ENVIRONMENT=production`
- `YAADHUM_STORAGE_BACKEND=s3`
- `YAADHUM_S3_BUCKET=yaadhum-scans-prod`
- `YAADHUM_S3_ACCESS_KEY_ID` / `YAADHUM_S3_SECRET_ACCESS_KEY` — the `yaadhum-app` keys
  from step 2, not your admin ones.
- `YAADHUM_S3_REGION=ap-south-1` (already the default)
- `YAADHUM_ANTHROPIC_API_KEY` — your Claude API key (note the `YAADHUM_` prefix; a bare
  `ANTHROPIC_API_KEY` is read by nothing — see `.env.example`'s own comment on this).
- `YAADHUM_CORS_ORIGINS=https://app.yourdomain.in`
- `YAADHUM_TRUSTED_HOSTS=api.yourdomain.in`
- `NEXT_PUBLIC_API_BASE=https://api.yourdomain.in`

Leave `YAADHUM_DATABASE_URL` / `YAADHUM_MIGRATION_DATABASE_URL` as whatever's in
`.env.example` — `docker-compose.yml` overrides both to point at the `postgres` service
by name, so what's in `.env` for those two is never actually used once you're running
under Compose.

## 6. Edit the Caddyfile

```bash
sed -i 's/yourdomain.in/YOURDOMAIN.in/g' Caddyfile   # your real domain, both lines
```

## 7. Build and start

```bash
docker compose up -d --build      # run from infra/, same as every command below
docker compose logs -f backend    # watch `alembic upgrade head` run, then uvicorn boot
```

The backend's own `CMD` already runs migrations before starting (see `backend/Dockerfile`)
— no separate migration step needed.

## 8. Verify

```bash
curl -s https://api.yourdomain.in/healthz          # {"status":"ok"}
curl -s https://api.yourdomain.in/health            # confirms DB connectivity too
```

Open `https://app.yourdomain.in`, sign in, scan a test paper, confirm the page image
loads (`GET /documents/{id}/pages/0` — proves the S3 wiring end to end) and that Tesseract
is actually present:

```bash
docker compose exec backend tesseract --list-langs   # should list eng, hin
```

## 9. Backups

```bash
sudo crontab -e
# add (as root, or whichever user's docker group membership lets it run `docker compose`):
0 2 * * * /srv/yaadhum/infra/backup-postgres.sh >> /var/log/yaadhum-backup.log 2>&1
```

This pushes a nightly `pg_dump` to `s3://yaadhum-scans-prod/db-backups/` — a prefix the
30-day lifecycle rule (scoped to `scans/` only) never touches, so backups accumulate
until you prune them yourself. `aws configure` needs to have run once for the `yaadhum-app`
IAM user's own session too, or attach an instance role instead of a static key — either
way, that user's policy above only covers `scans/*`; widen it to include `db-backups/*`
if you keep the same scoped user for backups.

## 10. Uptime monitoring (free)

**(console, external)** Add `https://api.yourdomain.in/healthz` and
`https://app.yourdomain.in` to a free tier at [UptimeRobot](https://uptimerobot.com) or
[healthchecks.io](https://healthchecks.io) — no AWS/CloudWatch cost for this at pilot
scale.

## Redeploying after a code change

```bash
cd /srv/yaadhum && git pull
docker compose up -d --build
```

## When to graduate off the single-VM Postgres

The day you'd be upset losing more than a night's data: switch
`YAADHUM_DATABASE_URL`/`YAADHUM_MIGRATION_DATABASE_URL` to a Lightsail Managed Database
(Postgres, ap-south-1) or RDS, `pg_dump`/restore once, drop the `postgres` service from
`docker-compose.yml`. No application code changes either way — it's SQLAlchemy against a
Postgres URL regardless of who runs the server.
