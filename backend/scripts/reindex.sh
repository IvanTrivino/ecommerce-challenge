#!/usr/bin/env bash
set -e
set -x

python -m app.search reindex "$@"
