#!/usr/bin/env python3
"""
ngx-l402 MCP server — let an agent buy API calls over L402.

Exposes two tools to any MCP client (Claude Desktop, etc.):

    list_paid_routes()                  -> the gateway's capability manifest
    call_paid_api(path, method, body)   -> pays the L402 invoice and returns
                                           the response body

Payment is automatic, from a Lightning node you control (LND REST), so the
agent never sees a key or a balance — it just calls the tool and gets data.

Configure via environment variables (see .env.example):

    L402_GATEWAY       base URL of the ngx-l402 gateway (default http://localhost:8000)
    LND_REST_URL       LND REST endpoint used to pay invoices, e.g. https://127.0.0.1:8080
    LND_MACAROON_HEX   hex macaroon with send permission (xxd -ps -c2000 admin.macaroon)
    LND_NO_VERIFY      set to any value to skip TLS verification (self-signed regtest certs)

Dependencies:  pip install -r requirements.txt
"""

import base64
import os
import re

import requests
from mcp.server.fastmcp import FastMCP

GATEWAY = os.environ.get("L402_GATEWAY", "http://localhost:8000").rstrip("/")
LND_REST_URL = os.environ.get("LND_REST_URL")
LND_MACAROON_HEX = os.environ.get("LND_MACAROON_HEX")
LND_VERIFY_TLS = os.environ.get("LND_NO_VERIFY", "") == ""

_FIELD_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

mcp = FastMCP("ngx-l402")


def _parse_challenge(header_value):
    fields = dict(_FIELD_RE.findall(header_value or ""))
    macaroon = fields.get("macaroon") or fields.get("token")
    invoice = fields.get("invoice")
    if not macaroon or not invoice:
        raise ValueError(f"could not parse L402 challenge: {header_value!r}")
    return macaroon, invoice


def _pay_invoice(invoice):
    if not (LND_REST_URL and LND_MACAROON_HEX):
        raise RuntimeError(
            "set LND_REST_URL and LND_MACAROON_HEX so the server can pay invoices"
        )
    resp = requests.post(
        f"{LND_REST_URL.rstrip('/')}/v1/channels/transactions",
        headers={"Grpc-Metadata-macaroon": LND_MACAROON_HEX},
        json={"payment_request": invoice},
        verify=LND_VERIFY_TLS,
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("payment_error"):
        raise RuntimeError(f"Lightning payment failed: {body['payment_error']}")
    return base64.b64decode(body["payment_preimage"]).hex()


@mcp.tool()
def list_paid_routes() -> str:
    """List the paid routes, prices, and payment backends this API advertises.

    Reads the gateway's /.well-known/l402-services capability manifest.
    """
    resp = requests.get(f"{GATEWAY}/.well-known/l402-services", timeout=15)
    resp.raise_for_status()
    return resp.text


@mcp.tool()
def call_paid_api(path: str, method: str = "GET", body: str = "") -> str:
    """Buy a single call to a paid API route over Lightning and return the body.

    Args:
        path:   route to call, e.g. "/protected" or "/v1/chat/completions"
        method: HTTP method (GET, POST, ...)
        body:   request body for POST/PUT (sent as application/json)

    The L402 invoice is paid automatically from the configured Lightning node.
    """
    url = f"{GATEWAY}{path}"
    session = requests.Session()
    headers = {"Content-Type": "application/json"} if body else {}
    data = body or None

    resp = session.request(method, url, headers=headers, data=data, timeout=60)
    if resp.status_code == 200:
        return resp.text
    if resp.status_code != 402:
        return f"error: HTTP {resp.status_code}: {resp.text[:500]}"

    macaroon, invoice = _parse_challenge(resp.headers.get("WWW-Authenticate", ""))
    preimage = _pay_invoice(invoice)

    paid_headers = dict(headers)
    paid_headers["Authorization"] = f"L402 {macaroon}:{preimage}"
    resp = session.request(method, url, headers=paid_headers, data=data, timeout=60)
    if resp.status_code != 200:
        return f"error after payment: HTTP {resp.status_code}: {resp.text[:500]}"
    return resp.text


if __name__ == "__main__":
    mcp.run()
