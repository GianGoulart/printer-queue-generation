#!/bin/sh
set -e

# Configure PYTHONPATH to include API code
# IMPORTANT: /app FIRST so worker modules take precedence
export PYTHONPATH="/app:/api_code:${PYTHONPATH}"

# Execute the command passed to the script
exec "$@"
