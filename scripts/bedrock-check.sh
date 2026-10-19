#!/usr/bin/env bash
# Calls every roster model once through the Bedrock Converse API.
# The first call to a third-party model also triggers Bedrock's automatic model enablement,
# so run this once with an admin profile before the first production game.
#   usage: scripts/bedrock-check.sh [region]
set -uo pipefail
REGION="${1:-${AWS_REGION:-us-west-2}}"
MODELS=(openai.gpt-oss-20b-1:0 google.gemma-3-27b-it mistral.magistral-small-2509 qwen.qwen3-32b-v1:0 deepseek.v3-v1:0)
status=0
for model in "${MODELS[@]}"; do
  printf '%-34s ' "$model"
  if reply=$(aws bedrock-runtime converse --region "$REGION" --model-id "$model" \
      --messages '[{"role":"user","content":[{"text":"Reply with exactly: ready"}]}]' \
      --inference-config '{"maxTokens":400}' \
      --query 'output.message.content[?text]|[0].text' --output text 2>&1); then
    echo "OK  -> ${reply:0:60}"
  else
    echo "FAIL -> ${reply:0:160}"; status=1
  fi
done
exit $status
