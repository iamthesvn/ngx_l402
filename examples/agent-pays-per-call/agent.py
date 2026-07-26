#!/usr/bin/env python3
"""
agent.py — an autonomous agent that pays per API call over L402.

The full machine-payable flow, with no API key and no human in the loop:

    1. (optional) discover the API by fetching /.well-known/l402-services
    2. GET a protected route            -> 402 Payment Required + invoice
    3. pay the Lightning invoice         -> preimage (proof of payment)
    4. retry with the preimage           -> 200 OK + the actual response

This is exactly the logic you would drop into an LLM tool / MCP server so an
agent can buy data on demand. Point it at any ngx-l402 gateway.

Payers (how step 3 happens):
    --payer manual    Print the invoice, you pay with any wallet, paste the
                      preimage back. Works against ANY gateway, zero setup.
    --payer lnd-rest  Pay autonomously via an LND REST node you control
                      (e.g. a funded regtest node, or your own mainnet node).

Usage:
    python agent.py --gateway http://localhost:8000 --path /protected
    python agent.py --gateway https://api.example.com --discover \
        --payer lnd-rest --lnd-rest-url https://127.0.0.1:8080 \
        --lnd-macaroon-hex $(xxd -ps -c2000 admin.macaroon) --lnd-no-verify

Only dependency: requests  (pip install -r requirements.txt)
"""

import argparse
import base64
import json
import re
import sys

import requests

# Box-glyph output (✓, →) crashes on Windows consoles using a legacy code page
# (cp1252). Force UTF-8 so the demo runs the same everywhere.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# ----------------------------------------------------------------------------
# tiny terminal helpers — the demo reads like a narrated transcript
# ----------------------------------------------------------------------------
def step(n, title):
    print(f"\n\033[1;34m[{n}]\033[0m \033[1m{title}\033[0m")

def info(msg):
    print(f"    {msg}")

def ok(msg):
    print(f"    \033[32m✓ {msg}\033[0m")

def warn(msg):
    print(f"    \033[33m! {msg}\033[0m")


# ----------------------------------------------------------------------------
# L402 protocol helpers
# ----------------------------------------------------------------------------
# A 402 carries the challenge in WWW-Authenticate, e.g.
#   WWW-Authenticate: L402 macaroon="AGIAJEem...", invoice="lnbc10u1p3..."
# bLIP-26 also allows `token=` as an alias for `macaroon=`.
_FIELD_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_challenge(header_value):
    """Return (macaroon, invoice) parsed from a WWW-Authenticate header."""
    fields = dict(_FIELD_RE.findall(header_value or ""))
    macaroon = fields.get("macaroon") or fields.get("token")
    invoice = fields.get("invoice")
    if not macaroon or not invoice:
        raise ValueError(
            f"could not parse macaroon/invoice from challenge: {header_value!r}"
        )
    return macaroon, invoice


def auth_header(macaroon, preimage=None):
    """Build the Authorization header for the retry.

    Classic flow:     L402 <macaroon>:<preimage_hex>
    Auto-detect flow: L402 <macaroon>            (server settles via node lookup)
    """
    if preimage:
        return f"L402 {macaroon}:{preimage}"
    return f"L402 {macaroon}"


# ----------------------------------------------------------------------------
# payers
# ----------------------------------------------------------------------------
def pay_manual(invoice):
    """Print the invoice and let a human pay it with any wallet."""
    info("Pay this invoice with any Lightning wallet, then paste the preimage:")
    print(f"\n    \033[36m{invoice}\033[0m\n")
    preimage = input("    preimage (64 hex chars): ").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", preimage):
        raise ValueError("expected a 32-byte (64 hex char) preimage")
    return preimage.lower()


def pay_lnd_rest(invoice, lnd_rest_url, macaroon_hex, verify_tls):
    """Pay autonomously via an LND REST node you control.

    POST /v1/channels/transactions  {"payment_request": "<bolt11>"}
    -> {"payment_preimage": "<base64>", "payment_error": ""}
    The macaroon needs send permission (admin.macaroon works).
    """
    resp = requests.post(
        f"{lnd_rest_url.rstrip('/')}/v1/channels/transactions",
        headers={"Grpc-Metadata-macaroon": macaroon_hex},
        json={"payment_request": invoice},
        verify=verify_tls,
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("payment_error"):
        raise RuntimeError(f"LND payment failed: {body['payment_error']}")
    preimage_b64 = body.get("payment_preimage")
    if not preimage_b64:
        raise RuntimeError(f"no preimage returned by LND: {body}")
    return base64.b64decode(preimage_b64).hex()


# ----------------------------------------------------------------------------
# main flow
# ----------------------------------------------------------------------------
def discover(session, gateway):
    """Fetch the capability manifest so the agent learns the API surface."""
    url = f"{gateway.rstrip('/')}/.well-known/l402-services"
    info(f"GET {url}")
    try:
        resp = session.get(url, timeout=15)
    except requests.RequestException as exc:
        warn(f"no manifest ({exc}); continuing without discovery")
        return None
    if resp.status_code != 200:
        warn(f"no manifest (HTTP {resp.status_code}); continuing without discovery")
        return None
    manifest = resp.json()
    methods = ", ".join(
        m.get("backend") or m.get("type") for m in manifest.get("payment_methods", [])
    )
    ok(f"discovered '{manifest.get('service', {}).get('name', 'API')}' — pays via {methods}")
    for route in manifest.get("routes", []):
        price = route.get("price", {}).get("amount_msat")
        info(f"  · {route.get('path')}  —  {price} msat")
    return manifest


def run(args):
    gateway = args.gateway
    target = f"{gateway.rstrip('/')}{args.path}"
    session = requests.Session()

    print(f"\033[1mngx-l402 · autonomous agent demo\033[0m")
    print(f"gateway: {gateway}   route: {args.path}   payer: {args.payer}")

    if args.discover:
        step(1, "Discover the API (capability manifest)")
        discover(session, gateway)

    step(2, "Request the protected route (no payment yet)")
    info(f"GET {target}")
    resp = session.get(target, timeout=15)
    if resp.status_code == 200:
        ok("already 200 OK — this route is not paywalled")
        print(resp.text)
        return 0
    if resp.status_code != 402:
        warn(f"expected 402, got {resp.status_code}: {resp.text[:200]}")
        return 1
    challenge = resp.headers.get("WWW-Authenticate", "")
    macaroon, invoice = parse_challenge(challenge)
    ok("402 Payment Required")
    info(f"macaroon: {macaroon[:40]}…")
    info(f"invoice:  {invoice[:40]}…")

    step(3, "Pay the Lightning invoice")
    preimage = None
    if args.payer == "manual":
        preimage = pay_manual(invoice)
    elif args.payer == "lnd-rest":
        if not (args.lnd_rest_url and args.lnd_macaroon_hex):
            warn("--payer lnd-rest needs --lnd-rest-url and --lnd-macaroon-hex")
            return 2
        preimage = pay_lnd_rest(
            invoice, args.lnd_rest_url, args.lnd_macaroon_hex, not args.lnd_no_verify
        )
        ok(f"paid — preimage {preimage[:24]}…")

    # In auto-detect mode the gateway settles via a node lookup, so the agent
    # can retry with just the macaroon (handy when the wallet hides preimages).
    retry_preimage = None if args.auto_detect else preimage

    step(4, "Retry with proof of payment")
    headers = {"Authorization": auth_header(macaroon, retry_preimage)}
    info(f"Authorization: {headers['Authorization'][:48]}…")
    resp = session.get(target, headers=headers, timeout=30)
    if resp.status_code != 200:
        warn(f"expected 200, got {resp.status_code}: {resp.text[:200]}")
        return 1
    ok("200 OK — paid response unlocked")
    print()
    try:
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print(resp.text)
    return 0


def main():
    p = argparse.ArgumentParser(description="Autonomous L402 pay-per-call agent")
    p.add_argument("--gateway", default="http://localhost:8000",
                   help="base URL of the ngx-l402 gateway")
    p.add_argument("--path", default="/protected",
                   help="protected route to buy (default: /protected)")
    p.add_argument("--discover", action="store_true",
                   help="fetch /.well-known/l402-services first")
    p.add_argument("--payer", choices=["manual", "lnd-rest"], default="manual",
                   help="how to pay the invoice")
    p.add_argument("--auto-detect", action="store_true",
                   help="retry with macaroon only (gateway has l402_auto_detect_payment on)")
    p.add_argument("--lnd-rest-url", help="LND REST endpoint, e.g. https://127.0.0.1:8080")
    p.add_argument("--lnd-macaroon-hex", help="hex-encoded macaroon with send permission")
    p.add_argument("--lnd-no-verify", action="store_true",
                   help="skip TLS verification (self-signed regtest certs)")
    args = p.parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — demo: surface the error plainly
        warn(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
