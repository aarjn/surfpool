# Railway deployment image for surfpool.
#
# Layers a Caddy reverse proxy (API-key auth + HTTP/WS routing on a single
# public port) on top of the official surfpool image, so Railway builds in
# seconds instead of compiling Rust from source.
#
# Build context is the repo root (see railway.json).

ARG SURFPOOL_IMAGE=surfpool/surfpool:latest

FROM caddy:2 AS caddy

FROM ${SURFPOOL_IMAGE}

COPY --from=caddy /usr/bin/caddy /usr/bin/caddy

COPY railway/Caddyfile /etc/caddy/Caddyfile
COPY railway/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Bind surfpool to loopback only — the API-key proxy is the sole way in.
ENV SURFPOOL_NETWORK_HOST=127.0.0.1

# Caddy listens on $PORT (default 8080); point your Railway domain at it.
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
  CMD curl --fail --silent --output /dev/null \
    --header 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
    http://127.0.0.1:8899

ENTRYPOINT ["/usr/local/bin/start.sh"]
