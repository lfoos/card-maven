#!/bin/bash
# Card Maven — start script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt --break-system-packages --quiet
fi

echo ""
echo "🃏  Card Maven is starting..."
echo "   Open http://localhost:5050 in your browser"
echo ""

python3 app.py
