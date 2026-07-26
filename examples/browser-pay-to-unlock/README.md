# Browser pay-to-unlock (WebLN)

A self-contained static page that runs the full L402 flow in the browser: it
requests a protected route, receives the `402` + Lightning invoice, pays it with
a [WebLN](https://www.webln.dev/) wallet (or any wallet), and unlocks the content
live — no build step, no backend, one HTML file.

```
[Request & pay] ─> GET /protected ─> 402 + invoice
                ─> webln.sendPayment(invoice) ─> preimage
                ─> GET /protected (Authorization: L402 macaroon:preimage) ─> 🔓 200
```

## Run it

Serve the file and open it (it's just static HTML):

```bash
python3 -m http.server 8080
# open http://localhost:8080/examples/browser-pay-to-unlock/
```

Set **Gateway URL** and **Protected path** to your ngx-l402 gateway, click
**Request & pay**, then **Pay with WebLN** (e.g. the [Alby](https://getalby.com)
extension). No WebLN wallet? Pay the shown invoice with any wallet — use **Open
in wallet** or scan it — then paste the 64-hex-char preimage to unlock.

## The CORS caveat (important)

The page reads the invoice from the `WWW-Authenticate` response header. Browsers
only expose that header to JavaScript when **either**:

1. the page is served from the **same origin** as the gateway (simplest — drop
   this file into the gateway's web root and open it there), **or**
2. the gateway sends CORS headers. Add to the protected `location` in
   `nginx.conf`:

   ```nginx
   add_header Access-Control-Allow-Origin  $http_origin always;
   add_header Access-Control-Expose-Headers WWW-Authenticate always;
   ```

Without one of these you'll see "Got 402 but cannot read WWW-Authenticate" — the
paywall is working, the browser is just hiding the header from the script.

## Notes

- WebLN returns the preimage directly (`sendPayment(invoice).preimage`), so the
  retry is automatic.
- This is a client only — it works against any ngx-l402 deployment, including
  the regtest dev stack in the
  [module repo](https://github.com/ngx-l402/ngx-l402).
