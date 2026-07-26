# Demo gateway

The live gateway behind the **"Try it live"** widget on [ngx-l402.org](https://ngx-l402.org):
a real ngx-l402 instance charging **1 sat** for `/protected`, with the CORS headers
browsers need to run the 402 → pay → unlock flow from a web page.

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
add_header Access-Control-Expose-Headers "WWW-Authenticate"       always;
```

`always` matters — without it nginx omits the headers on the 402 response, and
the widget shows "can't read WWW-Authenticate".

## Notes

- **1 sat pricing + per-IP invoice rate limiting** (`10r/m`) keep abuse boring.
- Payments settle to your `LNURL_ADDRESS` — the demo literally pays you.
- Redis gives replay protection across workers (and fails closed if down).
