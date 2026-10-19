#!/usr/bin/env bash
# Build + ship Outsmart to AWS using your local AWS credentials.
# Same steps as .github/workflows/deploy.yml, for the first deploy or when CI is not set up.
#   usage: scripts/deploy.sh            (run from the repo root, after `terraform apply`)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF="terraform -chdir=$ROOT/infra/terraform/envs/prod"
PY="$(command -v python3 || command -v python)"

out() { $TF output -raw "$1"; }
REGION="$(out region)"
ECR_URL="$(out ecr_repository_url)"
CLUSTER="$(out ecs_cluster)"
SERVICE="$(out ecs_service)"
FAMILY="$(out ecs_task_family)"
BUCKET="$(out site_bucket)"
DIST_ID="$(out cloudfront_distribution_id)"
APP_URL="$(out app_url)"
TAG="$(git -C "$ROOT" rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"

echo "==> Building image $ECR_URL:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR_URL%%/*}"
docker build --platform linux/amd64 -t "$ECR_URL:$TAG" "$ROOT"
docker push "$ECR_URL:$TAG"

echo "==> Registering task definition revision"
aws ecs describe-task-definition --task-definition "$FAMILY" --region "$REGION" --query taskDefinition > /tmp/outsmart-td.json
"$PY" - "$ECR_URL:$TAG" <<'PY'
import json, sys
td = json.load(open("/tmp/outsmart-td.json"))
td["containerDefinitions"][0]["image"] = sys.argv[1]
for key in ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
            "registeredAt", "registeredBy", "deregisteredAt"):
    td.pop(key, None)
json.dump(td, open("/tmp/outsmart-td-new.json", "w"))
PY
NEW_TD="$(aws ecs register-task-definition --region "$REGION" --cli-input-json file:///tmp/outsmart-td-new.json \
  --query taskDefinition.taskDefinitionArn --output text)"

echo "==> Rolling out $NEW_TD"
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$NEW_TD" --query service.serviceName --output text
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE"

echo "==> Publishing frontend to s3://$BUCKET"
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
aws s3 sync "$ROOT/frontend/dist" "s3://$BUCKET" --delete --exclude index.html \
  --cache-control "public,max-age=31536000,immutable"
aws s3 cp "$ROOT/frontend/dist/index.html" "s3://$BUCKET/index.html" --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/index.html" "/" --query Invalidation.Id --output text

echo "==> Smoke test"
for i in $(seq 1 20); do
  if curl -fsS "$APP_URL/api/health"; then echo; echo "Deployed: $APP_URL"; exit 0; fi
  sleep 15
done
echo "Health check did not pass yet - check CloudWatch logs: $(out log_group)" >&2
exit 1
