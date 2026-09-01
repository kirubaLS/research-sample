# Yaadhum on AWS

Mumbai (`ap-south-1`), because answer scripts are children's handwriting and the marks
derived from them are about named minors. Where that data **rests** is a DPDP Act
question, not a latency one. Every other choice here follows from that.

```
        internet
            │  HTTPS
      ┌─────▼─────┐
      │    ALB    │  public subnets, two AZs
      └─────┬─────┘
            │  HTTP :8000, security group to security group
      ┌─────▼─────────────┐
      │  ECS Fargate      │  private subnets, no public address
      │  api  ·  migrate  │
      └──┬─────────────┬──┘
         │             │  gateway endpoint, never over NAT
   ┌─────▼─────┐  ┌────▼──────┐
   │    RDS    │  │    S3     │  page images, one prefix per school
   │ Postgres  │  │  private  │
   └───────────┘  └───────────┘
```

## First time

```bash
cd infra/aws
terraform init
terraform apply -var pages_bucket_name=yaadhum-pages-<something-unguessable>
```

Then, once, write the database URL the app will use. RDS manages the master password, so
read it rather than inventing one:

```bash
SECRET=$(terraform output -raw database_master_secret_arn)
PASS=$(aws secretsmanager get-secret-value --secret-id "$SECRET" \
        --query SecretString --output text | python -c 'import json,sys;print(json.load(sys.stdin)["password"])')
HOST=$(terraform output -raw database_endpoint)

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw database_url_secret_arn)" \
  --secret-string "postgresql+psycopg://yaadhum:${PASS}@${HOST}:5432/yaadhum"
```

Then deploy:

```bash
./deploy.sh
```

## Deploying

`./deploy.sh` builds, pushes, **migrates as a one-off task**, waits for it to succeed, and
only then moves the service. If the migration fails the service is not touched and the old
tasks keep serving. That order is the whole reason the script exists.

Images are tagged with the commit, never `latest`, so a rollback names an exact image:

```bash
./deploy.sh <older-commit-sha>
```

## Before a real school's scripts go in

- [ ] **`certificate_arn` set.** Without it the listener is plain HTTP. Student data must
      not travel it, and nothing in this stack stops you.
- [ ] **`cors_origins` set to the exact web origin.** Never `*`: the student test route is
      unauthenticated by design.
- [ ] **`trusted_hosts` set** to the API's real hostname.
- [ ] **`db_multi_az = true`** before a second school's marks are in one database.
- [ ] **Backups checked by restoring one.** A backup nobody has restored is a belief.
      A term of marking cannot be redone.
- [ ] **`platform_admin_key_secret_arn` set** only if you want the operator console on.
      Unset means off, which is the right default.

## What is deliberately not here

**A domain and a certificate.** Both belong to whoever owns the name, and a Terraform run
that can issue certificates for a domain is a Terraform run that can take it over.

**Any secret value.** Terraform creates the secret *container*; the values are written
once with `aws secretsmanager put-secret-value`. A secret in a variable is a secret in
state, and state is a file people copy.

**The web app.** It is a static Next.js build; put it behind CloudFront with an S3 origin,
or run it as a second service. It holds no student data at rest, so it does not carry the
residency constraint the API does — but build it with `NEXT_PUBLIC_API_BASE` pointing at
the `api_url` output, because that value is baked in at build time and a restart will not
pick up a change.

## Cost, roughly, for one school

The NAT gateway and the ALB dominate and are charged by the hour whether or not anyone is
scanning; Fargate at 1 vCPU is the next line; RDS `t4g.micro` and S3 for a term of page
images are close to noise. `nat_per_az = false` is the deliberate saving: one NAT is a
failure mode that takes one school offline for minutes, and two costs the same again
every month.

## Verified, and not

The HCL parses and is formatted (`terraform fmt`). It has **not** been run against the AWS
provider — this environment cannot reach the Terraform registry, so resource arguments are
unvalidated against the provider schema. Run `terraform init && terraform validate` before
the first apply and expect to fix argument names.
