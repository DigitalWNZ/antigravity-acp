#!/bin/bash
# Wrapper that filters non-JSON lines from the server's stdout
# to prevent the Node.js browser opener from corrupting the ACP channel.
export BROWSER=""
export DISPLAY=""
exec "$@" 2>&2 | while IFS= read -r line; do
  # Only forward lines that start with { (JSON-RPC messages)
  if [[ "$line" == "{"* ]]; then
    printf '%s\n' "$line"
  else
    # Log non-JSON lines to stderr
    echo "[filtered] $line" >&2
  fi
done
