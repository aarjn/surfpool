# Deploy surfpool on Railway

Runs surfpool as a hosted RPC endpoint on [Railway](https://railway.com), gated by an
API key, with **HTTPS and WSS on the same URL**:

```
https://<your-domain>/?api-key=<key>   → JSON-RPC (port 8899 inside the container)
wss://<your-domain>/?api-key=<key>     → WebSocket pubsub (port 8900 inside the container)
```

How it works: the container runs the official `surfpool/surfpool` image bound to
loopback, plus a [Caddy](https://caddyserver.com) proxy listening on Railway's public
port. Caddy checks the API key, routes WebSocket upgrades to surfpool's pubsub server
and everything else to the JSON-RPC server, and serves an unauthenticated `/health`
for Railway's healthcheck. Railway's edge terminates TLS, so one domain gives you both
`https://` and `wss://`.

## Deploy

### From the dashboard

1. Push this repo (with the `railway/` directory and root `railway.json`) to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo** and pick the repo.
   `railway.json` picks the Dockerfile automatically. Two variants exist:
   - `railway/Dockerfile.source` (current default) — compiles surfpool from this
     repo, so local patches (e.g. the datasource retry fix in
     `crates/core/src/surfnet/remote.rs`) are included. Builds take 20-40 min.
   - `railway/Dockerfile` — layers the proxy on the prebuilt `surfpool/surfpool`
     Docker Hub image. Builds in seconds but only runs released surfpool code.
     Switch `dockerfilePath` in `railway.json` to use it.
3. In the service **Variables** tab, set:

   | Variable | Required | Purpose |
   |---|---|---|
   | `RPC_API_KEY` | ✅ | The API key clients must present. Generate: `openssl rand -hex 16` |
   | `SURFPOOL_NETWORK` | — | Fork source: `mainnet` (default), `devnet`, or `testnet` |
   | `SURFPOOL_DATASOURCE_RPC_URL` | — | Fork from a custom RPC (e.g. Helius) instead of `SURFPOOL_NETWORK` — set at most one of the two. Strongly recommended: the default public mainnet RPC rate-limits surfpool's lazy account fetches, which surfaces as failed transactions (e.g. during program deploys) |
   | `SURFPOOL_DB_URL` | — | SQLite path for persistent state, e.g. `/data/surfpool.sqlite` (attach a Railway volume mounted at `/data`) |
   | `SURFPOOL_EXTRA_ARGS` | — | Extra `surfpool start` flags, e.g. `--slot-time 400` |
   | `SURFPOOL_ENABLE_STUDIO` | — | Set to `1` to run Surfpool Studio (see note below) |

   Example, forking mainnet through Helius:

   ```
   RPC_API_KEY=<generated-with-openssl-rand>
   SURFPOOL_DATASOURCE_RPC_URL=https://mainnet.helius-rpc.com/?api-key=<your-helius-key>
   ```

4. **Settings → Networking → Generate Domain**, targeting port **8080**.
5. Wait for the deploy to go healthy, then test (below).

### From the CLI

```sh
railway init
railway variables --set "RPC_API_KEY=$(openssl rand -hex 16)"
railway up
railway domain   # create the public domain, target port 8080
```

## Use it

Shell (note the quotes — the URL contains `?`):

```sh
curl "https://<your-domain>/?api-key=<key>" -s \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getSlot"}'

# WebSocket
npx wscat -c "wss://<your-domain>/?api-key=<key>"
> {"jsonrpc":"2.0","id":1,"method":"slotSubscribe"}
```

Frontend / backend (`@solana/web3.js`):

```ts
const RPC = "https://<your-domain>/?api-key=<key>";
const WS  = "wss://<your-domain>/?api-key=<key>";
const connection = new Connection(RPC, { wsEndpoint: WS, commitment: "confirmed" });
```

`@solana/kit`:

```ts
const rpc = createSolanaRpc("https://<your-domain>/?api-key=<key>");
const rpcSubscriptions = createSolanaRpcSubscriptions("wss://<your-domain>/?api-key=<key>");
```

Browser clients should use the `?api-key=` query form (WebSockets can't set custom
headers). Non-browser clients may instead send the key as an `x-api-key` header.

Solana CLI / program deploys (the CLI derives the `wss://` URL automatically):

```sh
solana config set --url "https://<your-domain>/?api-key=<key>"
solana airdrop 100          # surfpool supports airdrops on the fork
solana program deploy target/deploy/my_program.so
```

Anchor (`Anchor.toml`):

```toml
[provider]
cluster = "https://<your-domain>/?api-key=<key>"
```

### Program deploys

**Recommended: the cheatcode deployer.** `solana program deploy` sends ~1 transaction
per KB of program; on a small hosted container that flood causes multi-second server
stalls, and any response slower than the CLI's ~30s timeout aborts the deploy with
`Error: ... error sending request for url (...)` (retrying can succeed — it's flaky,
not broken, and already-sent transactions do land). `write-program.py` instead installs
the program through surfpool's `surfnet_writeProgram` cheatcode in a few large RPC
calls — sub-second and reliable:

```sh
python3 railway/write-program.py target/deploy/my_program.so \
    target/deploy/my_program-keypair.json \
    "https://<your-domain>/?api-key=<key>" \
    <upgrade-authority pubkey or keypair.json>
```

If you prefer the standard CLI path anyway:

- Retry on `error sending request` failures, and consider raising the service's
  CPU/memory on Railway — the stalls are load-related.
- The CLI derives the WebSocket URL from the HTTP URL. With the Railway domain
  (no explicit port) this resolves correctly to `wss://<your-domain>/?api-key=<key>`.
  If you ever use a URL with an explicit port (e.g. local testing on `:8080`), the CLI
  assumes WS is on port+1 — pass `--ws "ws://<host>:<port>/?api-key=<key>"` explicitly.
- `--use-rpc` (`anchor deploy -- --use-rpc`) forces write transactions over HTTP
  instead of the TPU client; it does not avoid the stall-timeout issue.

## Notes

- **This is a simulated network.** Anyone with the key can airdrop, set accounts via
  `surfnet_*` cheatcodes, and reset state — treat the key as a secret, and don't point
  value-bearing keys at it.
- **Restarts reset state** unless you set `SURFPOOL_DB_URL` on a mounted Railway volume.
  Redeploys also rotate nothing about the key — the endpoint and key stay stable.
- **Studio**: `SURFPOOL_ENABLE_STUDIO=1` starts the Studio web UI on port 18488, but it
  is not behind the API key. To reach it you must also set `SURFPOOL_NETWORK_HOST=0.0.0.0`
  and add a second Railway domain targeting port 18488 — only do this if you accept that
  the Studio UI is public.
- Caddy replies `401` with a JSON-RPC-shaped error when the key is missing or wrong.

## Test locally

```sh
docker build -f railway/Dockerfile -t surfpool-railway .
docker run --rm -p 8080:8080 -e RPC_API_KEY=devkey surfpool-railway
curl "http://localhost:8080/?api-key=devkey" -s \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'
```
