#!/usr/bin/env bash
#
# Build, push, migrate, release. In that order, and stopping at the first failure.
#
# The order is the point. A migration that runs after the new tasks are already serving
# means requests hit a schema that does not exist yet; a migration that runs on container
# start means several tasks race to apply it. So: push the image, run migrations ONCE as a
# task, wait for it to succeed, and only then move the service.
#
#   ./deploy.sh                 # deploys the current commit
#   ./deploy.sh v2026-09-01     # deploys a tag you name
#
set -euo pipefail

cd "$(dirname "$0")"

REGION="${AWS_REGION:-ap-south-1}"
TAG="${1:-$(git rev-parse --short HEAD)}"

need() { command -v "$1" >/dev/null || { echo "need $1 on PATH"; exit 1; }; }
need aws
need docker
need terraform

out() { terraform output -raw "$1"; }

REPO=$(out ecr_repository_url)
CLUSTER=$(out cluster_name)
SERVICE=$(out service_name)
MIGRATE=$(out migrate_task_family)
SUBNETS=$(terraform output -json private_subnet_ids | tr -d '[]" ' )
SG=$(out api_security_group_id)

echo "==> building ${REPO}:${TAG}"
# linux/amd64 explicitly: an image built on an Apple laptop is arm64 and Fargate will pull
# it, start it, and fail with an exec format error that reads like a broken entrypoint.
docker build --platform linux/amd64 -t "${REPO}:${TAG}" ../../backend

echo "==> pushing"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"
docker push "${REPO}:${TAG}"

echo "==> registering task definitions at ${TAG}"
terraform apply -auto-approve -var "image_tag=${TAG}"

echo "==> migrating"
TASK=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$MIGRATE" \
  --launch-type FARGATE \
  --region "$REGION" \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG}],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' --output text)

aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK" --region "$REGION"

CODE=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" --region "$REGION" \
  --query 'tasks[0].containers[0].exitCode' --output text)
if [ "$CODE" != "0" ]; then
  echo "migration failed (exit ${CODE}). The service was NOT moved; the old tasks are"
  echo "still serving. Read the log group /ecs/* with the prefix 'migrate'."
  exit 1
fi

echo "==> releasing"
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$(terraform output -raw service_name)" \
  --region "$REGION" >/dev/null

# The circuit breaker rolls back a bad image on its own; this just waits so a deploy
# script that returns means the school is actually serving the new build.
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION"
echo "==> ${TAG} is live at $(out api_url)"
