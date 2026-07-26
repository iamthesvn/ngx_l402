# LLM API paywall

Put ngx-l402 in front of a local LLM so **every chat completion costs sats** —
no accounts, no API keys, no billing integration. Point any OpenAI-compatible
client at the gateway; unpaid calls get a `402` with a Lightning invoice, paid
calls stream the completion.

```
client ──> :8000 /v1/chat/completions ──(402 + invoice)
       ──> pay on Lightning ──> retry with preimage
       ──> ngx-l402 verifies ──> proxy_pass ──> Ollama ──> completion
```

The LLM (Ollama) never knows about Lightning — the paywall lives entirely in the
gateway's [`nginx.conf`](nginx.conf).

## Run it

```bash
cp .env.example .env
#  - set LNURL_ADDRESS to a Lightning address you control
#  - set ROOT_KEY=$(openssl rand -hex 32)

docker compose up -d

# Pull a small model (first time only):
docker compose exec ollama ollama pull llama3.2
```

## Try it

**Discovery (free):**

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8000/.well-known/l402-services
```

**A completion (paid):**

```bash
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"haiku about sats"}]}'
```

That returns:

```
HTTP/1.1 402 Payment Required
WWW-Authenticate: L402 macaroon="AgEEbDQ...", invoice="lnbc1u1p5..."
```

Pay the invoice, then retry with the preimage:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: L402 $MACAROON:$PREIMAGE" \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"haiku about sats"}]}'
```

> With the LNURL backend the invoice is **real** — you're paying your own
> Lightning address. Keep `l402_amount_msat_default` low (100 sats here) while
> testing, or point the gateway at the regtest dev stack for free play money.

## Let an agent buy completions

The [`mcp-paid-tool`](../mcp-paid-tool/) demo can call this endpoint directly, so
an agent buys a completion per request:

```python
call_paid_api(
    "/v1/chat/completions", "POST",
    '{"model":"llama3.2","messages":[{"role":"user","content":"hi"}]}'
)
```

## Tuning

| Want to… | Change |
|---|---|
| Set the price | `l402_amount_msat_default` in [`nginx.conf`](nginx.conf) (msat) |
| Price per-route dynamically | set `REDIS_URL` (already wired) and write the path key in Redis |
| Use your own node instead of LNURL | swap the `LN_CLIENT_TYPE` env block (see the [backend reference](https://ngx-l402.org/docs/lightning.html)) |
| Paywall a different upstream | change the `upstream` + `proxy_pass` in [`nginx.conf`](nginx.conf) |
