#!/usr/bin/env bash
# Rename asset files: remove sku_prefix (prefix-num-num-) and keep only design.
# Example: inf-1-6-unicorn-4.png -> unicorn-4.png
# Run from: /tmp/printer-queue-assets/tenant-2/tenant/2/assets (or set ASSETS_DIR)

set -e
ASSETS_DIR="${1:-/tmp/printer-queue-assets/tenant-2/tenant/2/assets}"
cd "$ASSETS_DIR"

# Only rename .png files that match: letters-num-num-... (strip the first 3 segments)
for f in *.png; do
  [ -f "$f" ] || continue
  # Remove prefix: one or more segments [a-z]+-[0-9]+-[0-9]+- at start
  newname=$(echo "$f" | sed -E 's/^[a-z]+-[0-9]+-[0-9]+-//')
  if [ "$f" != "$newname" ]; then
    if [ -e "$newname" ]; then
      echo "SKIP (target exists): $f -> $newname"
    else
      mv "$f" "$newname"
      echo "mv $f -> $newname"
    fi
  fi
done
echo "Done."
