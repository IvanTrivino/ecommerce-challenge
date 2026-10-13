#!/bin/sh
# Publishes a frontend build to the directory nginx serves, without downtime:
#   1. Copy every file except index.html. Hashed assets never collide, and the
#      previous ones are kept, so tabs still running the old version can load
#      their lazy (code-split) route chunks.
#   2. Swap index.html last, atomically (write a temp file, then rename).
#   3. Delete hashed assets that no release has shipped for ASSETS_RETENTION_DAYS.
# Usage: publish.sh <build dir> <target dir>
set -eu

SRC=$1
TARGET=$2
RETENTION_DAYS=${ASSETS_RETENTION_DAYS:-7}

if [ ! -f "$SRC/index.html" ]; then
  echo "No index.html in $SRC, refusing to publish" >&2
  exit 1
fi

mkdir -p "$TARGET"

for entry in "$SRC"/*; do
  [ "$(basename "$entry")" = "index.html" ] && continue
  # Overwriting refreshes the mtime of every file still in use (see step 3)
  cp -R "$entry" "$TARGET"/
done

cp "$SRC/index.html" "$TARGET/.index.html.new"
mv -f "$TARGET/.index.html.new" "$TARGET/index.html"

# Only the top level of assets/ holds Vite's hashed output; assets/images/ comes
# from frontend/public and is overwritten in place on every release.
if [ -d "$TARGET/assets" ]; then
  find "$TARGET/assets" -maxdepth 1 -type f -mtime +"$RETENTION_DAYS" -print -delete
fi

echo "Frontend published to $TARGET"
