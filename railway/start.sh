#!/usr/bin/env bash
# Railway entrypoint: runs surfpool (loopback-only) and Caddy (public,
# API-key gated) side by side; exits if either dies so Railway restarts us.
set -euo pipefail

if [ -z "${RPC_API_KEY:-}" ]; then
  echo "ERROR: RPC_API_KEY is not set." >&2
  echo "Set it in your Railway service variables. Generate one with: openssl rand -hex 16" >&2
  exit 1
fi

export PORT="${PORT:-8080}"

# Bind surfpool to loopback so the API-key proxy is the only way in.
export SURFPOOL_NETWORK_HOST="${SURFPOOL_NETWORK_HOST:-127.0.0.1}"

# Advertise the public Railway URLs in surfpool's startup output.
if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
  export SURFPOOL_PUBLIC_HOST="${SURFPOOL_PUBLIC_HOST:-${RAILWAY_PUBLIC_DOMAIN}}"
  export SURFPOOL_PUBLIC_RPC_URL="${SURFPOOL_PUBLIC_RPC_URL:-https://${RAILWAY_PUBLIC_DOMAIN}/?api-key=${RPC_API_KEY}}"
  export SURFPOOL_PUBLIC_WS_URL="${SURFPOOL_PUBLIC_WS_URL:-wss://${RAILWAY_PUBLIC_DOMAIN}/?api-key=${RPC_API_KEY}}"
fi

SURFPOOL_ARGS=(start --no-tui)

# Studio's web UI has no auth, so it stays off unless explicitly enabled.
if [ "${SURFPOOL_ENABLE_STUDIO:-0}" != "1" ]; then
  SURFPOOL_ARGS+=(--no-studio)
fi

# Fork source: SURFPOOL_NETWORK=mainnet|devnet|testnet, or set
# SURFPOOL_DATASOURCE_RPC_URL (read natively by surfpool) to fork from a
# custom RPC provider. Set at most one; default is a mainnet fork.
if [ -n "${SURFPOOL_NETWORK:-}" ]; then
  SURFPOOL_ARGS+=(--network "${SURFPOOL_NETWORK}")
fi

# Persistence, e.g. /data/surfpool.sqlite on a Railway volume.
if [ -n "${SURFPOOL_DB_URL:-}" ]; then
  SURFPOOL_ARGS+=(--db "${SURFPOOL_DB_URL}")
fi

if [ -n "${SURFPOOL_EXTRA_ARGS:-}" ]; then
  # shellcheck disable=SC2206
  SURFPOOL_ARGS+=(${SURFPOOL_EXTRA_ARGS})
fi

echo "Starting: surfpool ${SURFPOOL_ARGS[*]}"
surfpool "${SURFPOOL_ARGS[@]}" &
SURFPOOL_PID=$!

echo "Starting caddy on :${PORT}"
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
CADDY_PID=$!

terminate() {
  kill "$SURFPOOL_PID" "$CADDY_PID" 2>/dev/null || true
}
trap terminate TERM INT

code=0
wait -n || code=$?
terminate
exit "$code"
