#!/usr/bin/env bash
# Provision TLS certificates for the nginx reverse proxy (--profile prod).
#
# Two modes:
#   ./scripts/setup_tls.sh self-signed [common-name]
#       Generates a 10-year self-signed cert into nginx/certs/. Right choice
#       for intranet/on-prem deployments where clients trust the college CA
#       or accept the browser warning once.
#
#   ./scripts/setup_tls.sh letsencrypt <domain> <email>
#       One-time Let's Encrypt issuance via the webroot challenge. Requires
#       the domain to resolve to this server and port 80 to be reachable from
#       the internet. Renewal afterwards is automatic: the `certbot` compose
#       service re-runs `certbot renew` every 12h, and its deploy hook copies
#       fresh certs into nginx/certs/ where nginx picks them up on its
#       periodic reload.
set -euo pipefail

cd "$(dirname "$0")/.."
CERT_DIR="nginx/certs"
mkdir -p "$CERT_DIR"

mode="${1:-}"

self_signed() {
    local cn="${1:-attendance.internal}"
    echo ">> Generating self-signed certificate for CN=${cn} ..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
        -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
        -subj "/CN=${cn}"
    echo ">> Done. Start the stack with: docker compose --profile prod up -d"
}

letsencrypt() {
    local domain="${1:?usage: setup_tls.sh letsencrypt <domain> <email>}"
    local email="${2:?usage: setup_tls.sh letsencrypt <domain> <email>}"

    if [ ! -f "$CERT_DIR/cert.pem" ]; then
        echo ">> No cert yet — creating a temporary self-signed one so nginx can start."
        self_signed "$domain"
    fi

    echo ">> Starting nginx (needed to answer the ACME HTTP challenge) ..."
    docker compose --profile prod up -d nginx

    echo ">> Requesting certificate for ${domain} ..."
    # The deploy hook is recorded in the renewal config, so the long-running
    # `certbot` service's plain `certbot renew` re-runs it on every renewal.
    docker compose --profile prod run --rm --entrypoint certbot certbot certonly \
        --webroot -w /var/www/certbot \
        -d "$domain" \
        --email "$email" \
        --agree-tos --no-eff-email --non-interactive \
        --deploy-hook "cp /etc/letsencrypt/live/${domain}/fullchain.pem /certs/cert.pem && cp /etc/letsencrypt/live/${domain}/privkey.pem /certs/key.pem"

    echo ">> Reloading nginx with the new certificate ..."
    docker compose --profile prod exec nginx nginx -s reload

    echo ">> Done. Auto-renewal runs inside the 'certbot' service:"
    echo ">>   docker compose --profile prod up -d"
}

case "$mode" in
    self-signed)  self_signed "${2:-}";;
    letsencrypt)  letsencrypt "${2:-}" "${3:-}";;
    *)
        echo "usage: $0 self-signed [common-name]"
        echo "       $0 letsencrypt <domain> <email>"
        exit 1
        ;;
esac
