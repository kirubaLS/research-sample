# Yaadhum on one machine

For one school. Roughly a quarter of the Fargate stack's cost, because it has neither a
load balancer nor a NAT gateway, and it asks for that back in work you do yourself: you
patch the box, and you check the backups.

```
   internet
       │  :443, certificate held by Caddy
 ┌─────▼────────────────────────────┐
 │  one t4g.small, ap-south-1       │
 │                                  │
 │   caddy ──► api ──► postgres     │   /var/lib/yaadhum on its own EBS volume
 └───────────────┬──────────────────┘
                 │  instance role, no keys
           ┌─────▼─────┐
           │    S3     │  schools/  page images
           │           │  backups/  nightly dumps
           └───────────┘
```

Same image as production on Fargate. Moving between the two is a deploy target, not a
rewrite.

## First time

Point a domain at the address first, because Caddy asks for a certificate as it starts and
needs the name to resolve.

```bash
cd infra/ec2
terraform init
terraform apply -var bucket_name=yaadhum-<something-unguessable>   # no domain yet
# put an A record for your domain on the public_ip output, wait for it to resolve, then:
terraform apply -var bucket_name=yaadhum-<something-unguessable> -var domain=api.yourschool.in
```

Write the settings once. This is the only place a secret is typed:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw app_secret_arn)" \
  --secret-string "$(cat <<EOF
POSTGRES_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
YAADHUM_CORS_ORIGINS=https://yourschool.in
YAADHUM_TRUSTED_HOSTS=api.yourschool.in
YAADHUM_ANTHROPIC_API_KEY=sk-ant-...
YAADHUM_JINA_API_KEY=jina_...
YAADHUM_PLATFORM_ADMIN_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
EOF
)"
```

Then `./deploy.sh`.

## Day to day

```bash
./deploy.sh                 # build, push, restart. A few seconds of downtime: deploy after school.
./restore.sh                # put the newest backup back. Do this once before you need it.
aws ssm start-session --target "$(terraform output -raw instance_id)"   # a shell, no SSH
```

Backups run at 19:30 UTC — 01:00 IST, after the school day and before anyone is in. The
instance may **write** a backup and may not **delete** one; retention is the bucket's
lifecycle rule, so a mistake on the box cannot remove the history.

## What you are taking on

- **You patch it.** `dnf update` is not automatic. Put it in a calendar.
- **Deploys have downtime.** One instance, no load balancer, so the container restarts.
  Seconds, not minutes, but not zero.
- **The database is on one volume in one availability zone.** `prevent_destroy` is set on
  it and the nightly dump goes to S3, which is the real protection. If the AZ goes, you
  restore into a new instance from that dump.
- **Restore is not tested until you test it.** `restore.sh` exists so that is one command.
  A backup nobody has restored is a belief.

## When to leave

At about five schools, or the first time a deploy's downtime is a problem, or when one
school's load starts affecting another's. `infra/aws` is the same application with a load
balancer, rolling deploys and managed Postgres, and the image does not change.

## Verified, and not

The HCL parses and is formatted; both scripts pass `bash -n`. **None of it has been run** —
this environment has no AWS credentials, no Docker daemon and no access to the Terraform
registry, so resource arguments are unvalidated against the provider schema and the
user-data script has never booted a machine. Expect to fix things on the first apply.
