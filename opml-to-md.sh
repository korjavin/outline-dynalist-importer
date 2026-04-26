#!/bin/bash
# Convert every .opml file under the current directory to .md using pandoc.
# Run this from inside an unzipped Dynalist export folder.

set -euo pipefail

if ! command -v pandoc >/dev/null 2>&1; then
    echo "pandoc not found — install it first (brew install pandoc)" >&2
    exit 1
fi

find . -type f -name "*.opml" | while read -r file; do
    output_file="${file%.opml}.md"
    echo "Processing: $file -> $output_file"
    pandoc "$file" -f opml -t markdown -o "$output_file" --wrap=none
done

echo "Done! All OPML files have been converted to Markdown."
