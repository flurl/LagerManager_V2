#!/usr/bin/env bash
# Convert a Markdown file in this folder to PDF with working internal links
# (TOC, cross-references) and tables that wrap instead of overflowing the
# page margin.
#
# Usage:
#   ./md-to-pdf.sh [input.md]
#
# Defaults to fakturierung-handbuch.md. Output is written next to the input
# file with a .pdf extension. Requires: pandoc, lualatex (TeX Live), and the
# DejaVu Sans font.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT="${1:-$SCRIPT_DIR/fakturierung-handbuch.md}"
OUTPUT="${INPUT%.md}.pdf"

for cmd in pandoc lualatex; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: '$cmd' is required but not installed" >&2
    exit 1
  fi
done

pandoc --from=gfm "$INPUT" \
  -o "$OUTPUT" \
  --pdf-engine=lualatex \
  --lua-filter="$SCRIPT_DIR/table-widths.lua" \
  --resource-path="$SCRIPT_DIR" \
  -V lang=de \
  -V geometry:margin=2.5cm \
  -V mainfont="DejaVu Sans" \
  -V colorlinks=true \
  -V linkcolor=blue \
  -V urlcolor=blue

echo "Wrote $OUTPUT"
