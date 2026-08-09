#!/usr/bin/env bash
# Register this host as a LobeHub Market M2M client so LCA search_skill can auth.
# Credentials: ~/.lobehub-market/credentials.json (auto-read by lca.layer0_infra.skills.market_auth)
set -euo pipefail

NAME="${LCA_MARKET_CLIENT_NAME:-LCA-Agent}"
DESC="${LCA_MARKET_CLIENT_DESC:-Layered Cognitive Agent — operational skill marketplace consumer}"
SOURCE="${LCA_MARKET_CLIENT_SOURCE:-lca}"

echo "Registering M2M client: name=${NAME} source=${SOURCE}"
npx -y @lobehub/market-cli register \
  --name "${NAME}" \
  --description "${DESC}" \
  --source "${SOURCE}" \
  --output json

echo
echo "Verifying auth..."
npx -y @lobehub/market-cli auth status --output json || true
echo
echo "Done. LCA search_skill will use ~/.lobehub-market/credentials.json for Market search."
echo "Download/import by identifier still works without this registration."
