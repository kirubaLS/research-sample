#!/usr/bin/env bash
#
# Build, push, restart. No SSH: the restart goes through SSM, so there is no open port 22
# and no key to lose.
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
PLATFORM=$(out docker_platform)
INSTANCE=$(out instance_id)

echo "==> building ${REPO}:${TAG} for ${PLATFORM}"
# The platform comes from Terraform, not from this laptop: t4g is arm64, and an image
# built for the wrong one pulls, starts, and dies with an exec format error.
docker build --platform "${PLATFORM}" -t "${REPO}:${TAG}" ../../backend

echo "==> pushing"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"
docker push "${REPO}:${TAG}"

echo "==> restarting on ${INSTANCE}"
# One instance, so there is a few seconds of downtime here. That is the trade this option
# makes: no load balancer means no rolling deploy. Deploy after school.
CMD=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE" \
  --document-name "AWS-RunShellScript" \
  --comment "yaadhum deploy ${TAG}" \
  --parameters "commands=[\"set -e\",\"echo IMAGE_TAG=${TAG} > /opt/yaadhum/.env.tag\",\"cat /opt/yaadhum/.env.tag /opt/yaadhum/.env > /opt/yaadhum/.env.new || true\",\"mv /opt/yaadhum/.env.new /opt/yaadhum/.env\",\"IMAGE_TAG=${TAG} /usr/local/bin/yaadhum-up\"]" \
  --query 'Command.CommandId' --output text)

aws ssm wait command-executed --region "$REGION" --command-id "$CMD" --instance-id "$INSTANCE" || true

STATUS=$(aws ssm get-command-invocation --region "$REGION" \
  --command-id "$CMD" --instance-id "$INSTANCE" --query Status --output text)

if [ "$STATUS" != "Success" ]; then
  echo "deploy failed (${STATUS}). Output:"
  aws ssm get-command-invocation --region "$REGION" \
    --command-id "$CMD" --instance-id "$INSTANCE" \
    --query '[StandardOutputContent,StandardErrorContent]' --output text
  exit 1
fi

echo "==> ${TAG} is live at $(out url)"
