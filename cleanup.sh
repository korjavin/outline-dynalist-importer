#!/bin/bash
# Delete every .txt and .opml file under the current directory.
# Run this AFTER opml-to-md.sh, from inside the dynalist export folder.

set -euo pipefail

find . -type f \( -name "*.txt" -o -name "*.opml" \) -print -delete

echo "Done. Only .md files remain (folder structure preserved)."
