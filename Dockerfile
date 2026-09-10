ARG NGX_VERSION=1.28.0

# Build stage
FROM rust:1.93 AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y \
    pkg-config libssl-dev libclang-dev protobuf-compiler make libpcre2-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/bin/gpg /usr/bin/gpg2

COPY . .
ARG NGX_VERSION
ENV NGX_VERSION=${NGX_VERSION}
RUN curl -fsSL https://nginx.org/download/nginx-${NGX_VERSION}.tar.gz -o nginx.tar.gz \
    && tar -xzf nginx.tar.gz \
    && rm nginx.tar.gz \
    && cd nginx-${NGX_VERSION} \
    && ./configure --with-compat
ENV NGINX_SOURCE_DIR=/app/nginx-${NGX_VERSION}
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/app/target \
    cargo build --release --features export-modules \
    && cp target/release/libngx_l402_lib.so /tmp/libngx_l402_lib.so

# Runtime stage
FROM nginx:${NGX_VERSION}
EXPOSE 8000

COPY --from=builder /tmp/libngx_l402_lib.so /etc/nginx/modules/libngx_l402_lib.so
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/protected/index.html
COPY index.html /usr/share/nginx/html/protected-timeout/index.html
COPY index.html /usr/share/nginx/html/protected-indefinite/index.html
COPY index.html /usr/share/nginx/html/rate-limited/index.html
COPY index.html /usr/share/nginx/html/realm-a/index.html
COPY index.html /usr/share/nginx/html/realm-b/index.html
COPY index.html /usr/share/nginx/html/shadow/index.html
COPY index.html /usr/share/nginx/html/tenant1/index.html
COPY index.html /usr/share/nginx/html/tenant2/index.html

# Cashu state is split across two directories with different owners.
#
# The database must be writable by the workers. The mnemonic must not be: POSIX
# grants unlink to whoever can write a directory, whatever the file inside it is
# owned by, so a compromised worker sharing a directory with the phrase can
# replace it and receive every later payment into its own wallet. Mode 0600 and
# O_NOFOLLOW do not help — they protect the file, not the name.
#
# A mounted volume hides ownership set at build time, so the entrypoint sets it
# on every start, and migrates the flat layout earlier images used.
ENV CASHU_DB_PATH=/app/data/db/cashu_tokens.db \
    CASHU_WALLET_MNEMONIC_FILE=/app/data/secrets/wallet.mnemonic
# No `set -e` here: a skipped migration step must not leave the ownership
# below unapplied, and `[ ... ] && mv` under -e is exactly the shape that
# would do that.
RUN printf '%s\n' \
    '#!/bin/sh' \
    'd=$(dirname "${CASHU_DB_PATH:-/app/data/db/cashu_tokens.db}")' \
    's=$(dirname "${CASHU_WALLET_MNEMONIC_FILE:-/app/data/secrets/wallet.mnemonic}")' \
    'mkdir -p "$d" "$s" || exit 1' \
    '' \
    '# Pre-split volumes kept everything in one nginx-owned directory.' \
    'for f in wallet.mnemonic wallet.fingerprint; do' \
    '  if [ -f "/app/data/$f" ] && [ ! -e "$s/$f" ]; then' \
    '    mv "/app/data/$f" "$s/$f"' \
    '  fi' \
    'done' \
    'for f in /app/data/cashu_tokens.db*; do' \
    '  if [ -f "$f" ] && [ ! -e "$d/$(basename "$f")" ]; then' \
    '    mv "$f" "$d/"' \
    '  fi' \
    'done' \
    '' \
    'chown -R nginx:nginx "$d"' \
    'chmod 750 "$d"' \
    '' \
    '# root-owned and 0700. The master resolves the mnemonic in init_module,' \
    '# before it forks, so no worker ever needs to read this — and a worker that' \
    '# could write the directory could replace the phrase whatever the file mode.' \
    'chown -R root:root "$s"' \
    'chmod 700 "$s"' \
    'find "$s" -type f -exec chmod 600 {} +' \
    'exit 0' \
    > /docker-entrypoint.d/05-cashu-data-perms.sh \
    && chmod +x /docker-entrypoint.d/05-cashu-data-perms.sh

USER root

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
