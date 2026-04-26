# outline-dynalist-importer

End-to-end pipeline for importing a [Dynalist](https://dynalist.io/) backup
into a self-hosted [Outline](https://www.getoutline.com/) instance, preserving
the outline hierarchy as nested bullet lists and the folder structure as
parent documents.

## Why

Dynalist's "Backup all documents" produces a zip with `.opml` and `.txt` per
node. Outline imports markdown. The two formats don't line up:

- Dynalist items have arbitrary nesting depth (8+ levels are common).
- Pandoc's `opml -> markdown` converter renders each outline level as a
  heading (`#`, `##`, `###`, …). That looks wrong in a knowledge base — it
  produces a document of dozens of giant headings instead of a list.
- Outline's native answer for "indented list" is a nested bullet list.

So the pipeline is: OPML -> markdown (headings) -> markdown (nested bullets)
-> Outline documents.

## Pipeline

```
+-----------------+   opml-to-md.sh    +-----------------+
| Dynalist export |  ---------------+  | .md (headings)  |
| (.opml + .txt)  |                 |  +-----------------+
+-----------------+                 |
                                    |  cleanup.sh
                                    v
                          +--------------------+   import.py
                          | folder of *.md     |  ---------> Outline collection
                          | (folder hierarchy) |              (nested bullets,
                          +--------------------+               folder = parent doc)
```

## Requirements

- `pandoc` (`brew install pandoc`)
- Python 3.10+
- An Outline API key (Settings -> API & Apps)

## Usage

```sh
# 0. Download and unzip the Dynalist backup, then cd into it
cd ~/Downloads/dynalist-backup-YYYY-MM-DD

# 1. Convert OPML -> Markdown (one .md per .opml, in place)
~/path/to/outline-dynalist-importer/opml-to-md.sh

# 2. Drop .txt and .opml (keeping only .md and folders)
~/path/to/outline-dynalist-importer/cleanup.sh

# 3. Configure the importer (one-time)
cp ~/path/to/outline-dynalist-importer/.env.example ./.env
$EDITOR ./.env

# 4. Import
python3 ~/path/to/outline-dynalist-importer/import.py
```

The importer reads `.env` from the current working directory, so step 3 puts
the config next to the data.

## Configuration

| Variable                    | Required | Default    | Notes                                                                                          |
| --------------------------- | -------- | ---------- | ---------------------------------------------------------------------------------------------- |
| `OUTLINE_URL`               | yes      | -          | e.g. `https://outline.example.com`                                                             |
| `OUTLINE_API_KEY`           | yes      | -          | Starts with `ol_api_`                                                                          |
| `SOURCE_FOLDER`             | yes      | -          | Absolute path to the dynalist export folder                                                    |
| `OUTLINE_COLLECTION_NAME`   | no       | `dynalist` | Created if it doesn't exist                                                                    |
| `REQ_DELAY`                 | no       | `5.0`      | Seconds between API calls. Outline rate-limits documents.create per minute; 5s (~12/min) works |

## What the importer does

For each folder under `SOURCE_FOLDER`:
- Creates a parent document named after the folder.
- Recurses into subfolders, attaching them to the parent.

For each `.md` file:
- Strips any YAML frontmatter (the `obsidian-outline` plugin leaves
  `outline_id` metadata behind on prior pushes; this gets stripped).
- Converts every heading line `^#{n} text` to a bullet indented `n-1` levels.
- Preserves body text under a heading as a child bullet one level deeper
  (URLs and notes pandoc renders as paragraphs between headings).
- Skips empty headings (Dynalist often leaves trailing blank items).
- Creates the document under the right parent.

On HTTP 429 from Outline, the importer waits ~65s (one rate-limit window)
and retries up to 8 times.

## Re-running

The importer always creates new documents - there is no "update by title"
mode. If you want a clean re-run, delete the collection in Outline first
(or via API: `POST /api/collections.delete`).

## Acknowledgements

The OPML conversion approach was inspired by usage patterns of the
[obsidian-outline](https://github.com/defcon1702/obsidian-outline) plugin.
This repo intentionally avoids that plugin's dependency on Obsidian and its
heading-shape source documents - Dynalist exports are all hierarchy and no
prose, which fits nested bullets better.
