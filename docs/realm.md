# Realms (One Payment, Many Paths)

By default a payment buys **one exact URL**. The macaroon carries a
`RequestPath = /article/1` caveat, so the token that unlocked `/article/1` is
rejected on `/article/2` — the client pays again. That is the right model for
metered, per-resource pricing.

A **realm** changes the unit of sale. With `l402_realm "name";` the macaroon
carries `Realm = name` instead of a path, and one payment authorizes **every
path the server maps to that realm** — a subscription or day-pass, rather than
a per-article charge.

---

## Enabling a realm

```nginx
location /premium/ {
    l402                        on;
    l402_realm                  "premium";     # one payment covers this location
    l402_indefinite_access      on;            # REQUIRED — see below
    l402_macaroon_timeout       86400;         # 24h pass
    l402_amount_msat_default    50000;
    proxy_pass                  http://upstream;
}
```

A client pays once at `/premium/anything`, then reuses the same
`Authorization: L402 <macaroon>:<preimage>` header across every path under
`/premium/` until the macaroon expires.

### The realm name

The name goes verbatim into the `Realm = <name>` caveat and is compared by exact
match. It must be non-empty and contain no whitespace or control characters —
nginx **fails to start** otherwise, rather than silently accepting an ambiguous
caveat:

```
l402_realm requires a non-empty name without whitespace
```

Pick a stable identifier (`premium`, `api-tier-1`). Changing the name
invalidates every token already issued under the old one.

---

## `l402_indefinite_access on` is mandatory

A realm token carries **one preimage** to every path in the realm. Preimage
replay protection is single-use by design: the first request claims the
preimage, and every later request in the realm is rejected as a replay. The
operator would have sold exactly one request.

So the module refuses the combination at config-parse time. Omit it and nginx
will not start:

```
ngx_l402: l402_realm requires l402_indefinite_access on. Without it the realm
token is accepted once and every later request in the realm is rejected as a
replay.
```

This is a deliberate fail-closed check: the broken configuration is rejected
loudly at startup instead of silently short-changing users at runtime.

---

## Bounding a realm token

Because `l402_indefinite_access on` disables single-use replay protection, the
macaroon's own lifetime becomes the only limit on how long a payment stays
valid. **Always pair a realm with `l402_macaroon_timeout`:**

```nginx
l402_macaroon_timeout  86400;   # 24 hours
```

With the default `l402_macaroon_timeout 0;` the macaroon never expires and a
single payment authorizes the realm forever.

---

## What stays bound

Switching to a realm relaxes the *path* binding only. Everything else still
holds:

| Caveat | Realm mode | Default (path) mode |
|---|---|---|
| Protection space | `Realm = name` | `RequestPath = /exact` |
| HTTP method | Bound — a `GET` token is rejected on `POST` | Bound |
| Expiry | `ExpiresAt` when `l402_macaroon_timeout > 0` | Same |

All three are enforced by **exact match**, and the verifier explicitly rejects
these predicates rather than letting them fall through — a token minted for one
realm, path, or method can never validate against another.

---

## The name is the whole boundary

Two things follow from the realm being a flat, name-keyed protection space:

- **A realm is not bound to a price.** If two locations share a name but set
  different `l402_amount_msat_default`, a token bought at the cheaper one opens
  the dearer one — the caveat records only the name. Give differently-priced
  content **different realm names**.
- **Anything naming the realm is reachable with one payment.** Prefer specific
  names (`library-2026`) over generic ones (`api`), so a realm added later
  cannot accidentally join an existing protection space.

---

## Inheritance

`l402_realm` inherits into nested locations. An inner location can join the
parent's realm by inheriting it, or define its own to carve out a separate
protection space:

```nginx
location /premium/ {
    l402                    on;
    l402_realm              "premium";
    l402_indefinite_access  on;
    l402_macaroon_timeout   86400;

    location /premium/vip/ {
        l402_realm          "premium-vip";   # separate space, separate payment
        l402_amount_msat_default 200000;
    }
}
```

A `premium` token is **not** accepted at `/premium/vip/` — the `Realm` caveats
differ, so verification fails and the client is charged the VIP price.

---

## Choosing between realm and path mode

| Use | When |
|---|---|
| Default (path) | Metered per-resource pricing — pay-per-article, pay-per-API-call, pay-per-download |
| Realm | Subscriptions and passes — one payment unlocks a whole section for a period |

Realms are opt-in. Locations without `l402_realm` keep exact-path binding.
