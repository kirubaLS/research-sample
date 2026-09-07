#!/usr/bin/env bash
# Nightly Postgres backup, pushed to the same S3 bucket the scanned pages live in but
# under a prefix the 30-day lifecycle rule (infra/s3-lifecycle.json) never touches --
# extracted marks and questions are the permanent record and must outlive that expiry.
# Install: crontab -e, add a line like
#   0 2 * * * /srv/yaadhum/infra/backup-postgres.sh >> /var/log/yaadhum-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")"          # infra/ -- where docker-compose.yml and .env both live
set -a; source .env; set +a   # for YAADHUM_S3_BUCKET below; `docker compose` reads it separately

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="/tmp/yaadhum-${STAMP}.sql.gz"

docker compose exec -T postgres pg_dump -U yaadhum yaadhum | gzip > "$FILE"

# --sse AES256: server-side encrypted at rest, matching S3ObjectStore.put's own
# ServerSideEncryption setting for scanned pages (app/storage.py).
aws s3 cp "$FILE" "s3://${YAADHUM_S3_BUCKET}/db-backups/${STAMP}.sql.gz" \
    --region ap-south-1 --sse AES256

rm -f "$FILE"

# Keep local disk from filling on top of what S3 already has -- delete backups this VM
# made more than 3 days ago; S3 is the durable copy, not this directory.
find /tmp -maxdepth 1 -name 'yaadhum-*.sql.gz' -mtime +3 -delete
