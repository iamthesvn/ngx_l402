# Demo gateway

The live gateway behind the **"Try it live"** widget on [ngx-l402.org](https://ngx-l402.org):
a real ngx-l402 instance charging **1 sat** for `/protected`, with the CORS headers
browsers need to run the 402 → pay → unlock flow from a web page.

Two ways to pay the same route: a Lightning invoice, or a Cashu token in `X-Cashu`.

## Run it

```bash
cp ../llm-api-paywall/.env.example .env   # or create .env with:
#   LNURL_ADDRESS=you@getalby.com          ← the sats land here
#   ROOT_KEY=<openssl rand -hex 32>

docker compose up -d

curl -i http://localhost:8000/protected     # → 402 + Lightning invoice
```

Point the website widget at `http://localhost:8000` and pay the 1-sat invoice —
or put this behind `demo.ngx-l402.org` (DNS A record → your host, TLS via a
reverse proxy or Fly/Railway's built-in certs) so the widget's default URL works
for every visitor.

## The CORS part (the only non-obvious bit)

Browsers can only read the `WWW-Authenticate` challenge cross-origin if the
gateway says so. [`nginx.conf`](nginx.conf) already does this:

```nginx
add_header Access-Control-Allow-Origin  $http_origin              always;
add_header Access-Control-Allow-Headers "Authorization, X-Cashu"  always;
add_header Access-Control-Expose-Headers "WWW-Authenticate, X-Cashu" always;
```

`always` matters — without it nginx omits the headers on the 402 response, and
the widget shows "can't read WWW-Authenticate". `X-Cashu` is exposed as well as
allowed, because in P2PK mode the gateway returns its NUT-24 payment request in
that header and the browser cannot read it otherwise.

## Paying with Cashu

The same `/protected` route takes a Cashu token instead of a preimage:

```bash
curl -i http://localhost:8000/protected -H "X-Cashu: cashuB..."
```

The token must come from a mint in `CASHU_WHITELISTED_MINTS` and cover the 1-sat
price. The whitelist is what makes the route safe to expose — without it anyone
can present tokens from a mint they run themselves and get in for free. The list
lives in [`docker-compose.yml`](docker-compose.yml); it ships with one mint, and
which mints you trust is your call.

Received tokens accumulate in the `cashu` volume, and a wallet phrase is
generated there on first run. That is real value: back the volume up, or set
`CASHU_WALLET_MNEMONIC` yourself. To sweep the balance to Lightning
automatically, add `CASHU_REDEEM_ON_LIGHTNING=true` — at 1 sat a request it
won't fire until the balance clears `CASHU_MELT_MIN_BALANCE_SATS` (10 by
default).

This runs in standard mode, where the module swaps each token at the mint. P2PK
mode verifies locally and is much faster, but needs a private key on the gateway
and a wallet that can lock tokens to it — see [the Cashu
docs](https://ngx-l402.org/docs/cashu.html).

## Notes

- **1 sat pricing + per-IP invoice rate limiting** (`10r/m`) keep abuse boring.
- Payments settle to your `LNURL_ADDRESS` — the demo literally pays you.
- Redis gives replay protection across workers (and fails closed if down).
