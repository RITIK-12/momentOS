#!/usr/bin/env bash
# Deploy MomentOS on-cluster (deploy-app-no-registry pattern): public python image, code from a
# ConfigMap, credentials from a Secret, Ingress at http://<team host>/app. Team namespace only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECTL="${KUBECTL:-kubectl}"
export KUBECONFIG="${KUBECONFIG:-$(ls /config/kubeconfig /config/*-k8s.yaml 2>/dev/null | head -1)}"

mapfile -t TEAM_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
(( ${#TEAM_CONFIGS[@]} == 1 )) || { echo "expected exactly one /config/*.config"; exit 1; }
set -a && source "${TEAM_CONFIGS[0]}" && set +a

NS="$USERNAME"
APP_NAME=momentos
APP_PORT=8080
# Ingress host is the origin name from INGRESS_URL. Cloudflare serves the public
# name (team-49-vss.thecosmoslabs.com) and forwards to that origin with the lab Host.
APP_HOST="${INGRESS_URL#http://}"; APP_HOST="${APP_HOST#https://}"; APP_HOST="${APP_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST:-team-49-vss.thecosmoslabs.com}"

size=$(du -cb "$ROOT/app/main.py" "$ROOT/app/requirements.txt" "$ROOT/app/static/index.html" "$ROOT/app/static/data.json" | tail -1 | cut -f1)
(( size < 1000000 )) || { echo "app payload is ${size} bytes; ConfigMap limit is ~1 MiB"; exit 1; }
echo "namespace=$NS host=$APP_HOST payload=${size}B"

"$KUBECTL" -n "$NS" create configmap "${APP_NAME}-code" \
  --from-file=main.py="$ROOT/app/main.py" \
  --from-file=requirements.txt="$ROOT/app/requirements.txt" \
  --from-file=index.html="$ROOT/app/static/index.html" \
  --from-file=data.json="$ROOT/app/static/data.json" \
  --dry-run=client -o yaml | "$KUBECTL" apply --server-side --force-conflicts --field-manager=momentos-deploy -f -

# Pods cannot resolve the public ingress hostname; talk to the in-cluster backend Service.
VSS_INTERNAL="${VSS_INTERNAL:-http://video-backend-service:8000}"

"$KUBECTL" -n "$NS" create secret generic "${APP_NAME}-vss-creds" \
  --from-literal=VSS_URL="$VSS_INTERNAL" \
  --from-literal=VSS_USERNAME="$USERNAME" \
  --from-literal=VSS_PASSWORD="$PASSWORD" \
  --from-literal=WANDB_API_KEY="${WANDB_API_KEY:-}" \
  --from-literal=WANDB_TEAM="${WANDB_TEAM:-}" \
  --from-literal=WANDB_PROJECT="${WANDB_PROJECT:-}" \
  --dry-run=client -o yaml | "$KUBECTL" apply -f - >/dev/null
echo "secret/${APP_NAME}-vss-creds configured"

sed -e "s/__APP_NAME__/${APP_NAME}/g" -e "s/__APP_PORT__/${APP_PORT}/g" -e "s/__APP_HOST__/${APP_HOST}/g" \
  "$ROOT/deploy/momentos.yaml" | "$KUBECTL" -n "$NS" apply -f -

"$KUBECTL" -n "$NS" rollout restart deploy/"$APP_NAME"
"$KUBECTL" -n "$NS" rollout status deploy/"$APP_NAME" --timeout=240s
echo "MomentOS: http://${PUBLIC_HOST}/app"
