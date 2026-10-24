#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "Use: sudo ./install.sh" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"

"$ROOT/install/01-packages.sh"
"$ROOT/install/02-configure.sh"
"$ROOT/install/03-services.sh"

echo
echo "cameras-cassa installation complete."
echo "See docs/setup.md for validation and Google Drive OAuth."
