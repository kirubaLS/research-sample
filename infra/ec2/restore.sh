#!/usr/bin/env bash
#
# Restore the newest backup, or one you name. Here because a backup nobody has restored is
# a belief rather than a backup, and the time to find that out is not the week it matters.
#
#   ./restore.sh                                  # newest
#   ./restore.sh yaadhum-20260901T193000Z.dump.gz  # a specific one
#
set -euo pipefail
cd "$(dirname "$0")"

REGION="${AWS_REGION:-ap-south-1}"
BUCKET=$(terraform output -raw bucket)
INSTANCE=$(terraform output -raw instance_id)

KEY="${1:-}"
if [ -z "$KEY" ]; then
  KEY=$(aws s3 ls "s3://${BUCKET}/backups/" --region "$REGION" | sort | tail -1 | awk '{print $4}')
fi
[ -n "$KEY" ] || { echo "no backup found in s3://${BUCKET}/backups/"; exit 1; }

echo "This REPLACES the live database with ${KEY}."
read -r -p "Type the school's name to confirm: " _confirm
[ -n "${_confirm}" ] || exit 1

CMD=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"set -e\",\"aws s3 cp s3://${BUCKET}/backups/${KEY} /tmp/restore.dump.gz --region ${REGION}\",\"gunzip -f /tmp/restore.dump.gz\",\"docker compose -f /opt/yaadhum/compose.yaml cp /tmp/restore.dump db:/tmp/restore.dump\",\"docker compose -f /opt/yaadhum/compose.yaml exec -T db pg_restore -U yaadhum -d yaadhum --clean --if-exists /tmp/restore.dump\",\"rm -f /tmp/restore.dump\"]" \
  --query 'Command.CommandId' --output text)

aws ssm wait command-executed --region "$REGION" --command-id "$CMD" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD" --instance-id "$INSTANCE" \
  --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
