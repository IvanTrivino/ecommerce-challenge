#! /usr/bin/env bash
# Self-signed certificate so compose.prod.yml (nginx with HTTPS) can run on
# your machine. Writes ./certs/live/localhost/{fullchain,privkey}.pem; use with
# DOMAIN=localhost and CERTS_DIR=./certs (see .env.prod.example).
set -e
dir="$(dirname "$0")/../certs/live/localhost"
mkdir -p "$dir"
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout "$dir/privkey.pem" -out "$dir/fullchain.pem" \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"
