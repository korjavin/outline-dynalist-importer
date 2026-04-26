#!/usr/bin/env python3
"""
Import a tree of markdown files into an Outline collection.

Tailored to Dynalist exports: each `# / ## / ###` heading is treated as an
outline depth and converted to a nested bullet (`- ` indented by 2 spaces per
level). Empty headings are skipped. Folders become parent documents.

Configuration via environment variables (or a `.env` file in the current dir):

  OUTLINE_URL              required, e.g. https://outline.example.com
  OUTLINE_API_KEY          required, starts with `ol_api_...`
  SOURCE_FOLDER            required, path to the dynalist export folder
  OUTLINE_COLLECTION_NAME  optional, defaults to "dynalist"
                           (collection is created if it doesn't exist)
  REQ_DELAY                optional, seconds between API calls (default 5.0)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


def load_dotenv(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: missing env var {name}", file=sys.stderr)
        sys.exit(1)
    return val or ""


HEADING_RE = re.compile(r"^(#{1,12})\s*(.*)$")
FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def convert(md: str) -> str:
    md = FRONTMATTER_RE.sub("", md, count=1)
    out = []
    for line in md.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        depth = len(m.group(1)) - 1
        text = m.group(2).strip()
        if not text:
            continue
        out.append("  " * depth + "- " + text)
    return "\n".join(out) + ("\n" if out else "")


class Outline:
    def __init__(self, base_url: str, api_key: str, req_delay: float):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.req_delay = req_delay

    def call(self, endpoint: str, body: dict, max_retries: int = 8) -> dict:
        data = json.dumps(body).encode()
        for attempt in range(max_retries):
            req = urllib.request.Request(
                f"{self.base_url}/api/{endpoint}",
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    wait = 65
                    print(
                        f"  rate limited, sleeping {wait}s (attempt {attempt + 1}/{max_retries})",
                        flush=True,
                    )
                    time.sleep(wait)
                    continue
                # 5xx is a backend hiccup; 404 from Outline's edge during a
                # restart is the LB's "no route" page, not a missing resource.
                if (e.code == 404 or 500 <= e.code < 600) and attempt < max_retries - 1:
                    wait = min(30, 2 ** attempt)
                    print(
                        f"  HTTP {e.code}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})",
                        flush=True,
                    )
                    time.sleep(wait)
                    continue
                body_text = e.read().decode(errors="replace")
                raise RuntimeError(f"{endpoint} -> HTTP {e.code}: {body_text}") from e
            except urllib.error.URLError:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise
        raise RuntimeError("unreachable")

    def auth_info(self) -> dict:
        return self.call("auth.info", {})

    def find_or_create_collection(self, name: str) -> str:
        res = self.call("collections.list", {"limit": 100})
        for c in res.get("data", []):
            if c.get("name", "").lower() == name.lower():
                print(f"Using existing collection {name!r} -> {c['id']}")
                return c["id"]
        print(f"Creating collection {name!r}")
        res = self.call(
            "collections.create",
            {"name": name, "permission": "read_write"},
        )
        return res["data"]["id"]

    def create_doc(
        self, title: str, text: str, collection_id: str, parent_id: str | None
    ) -> str:
        body = {
            "title": title,
            "text": text,
            "collectionId": collection_id,
            "publish": True,
        }
        if parent_id:
            body["parentDocumentId"] = parent_id
        res = self.call("documents.create", body)
        if not res.get("ok"):
            raise RuntimeError(f"create failed: {res}")
        time.sleep(self.req_delay)
        return res["data"]["id"]


def walk(
    api: Outline,
    collection_id: str,
    path: str,
    parent_id: str | None,
    indent: int = 0,
) -> tuple[int, int]:
    entries = sorted(os.listdir(path))
    dirs = [
        e
        for e in entries
        if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")
    ]
    files = [
        e
        for e in entries
        if e.endswith(".md") and os.path.isfile(os.path.join(path, e))
    ]

    succ, fail = 0, 0
    pad = "  " * indent

    for d in dirs:
        full = os.path.join(path, d)
        print(f"{pad}[D] {d}", flush=True)
        try:
            doc_id = api.create_doc(d, "", collection_id, parent_id)
            s, f = walk(api, collection_id, full, doc_id, indent + 1)
            succ += s + 1
            fail += f
        except Exception as e:
            print(f"{pad}  folder doc failed: {e}", flush=True)
            fail += 1

    for fname in files:
        full = os.path.join(path, fname)
        title = fname[:-3]
        with open(full, encoding="utf-8") as fh:
            md = fh.read()
        text = convert(md)
        try:
            api.create_doc(title, text, collection_id, parent_id)
            print(f"{pad}    {title}", flush=True)
            succ += 1
        except Exception as e:
            print(f"{pad}    {title} FAILED: {e}", flush=True)
            fail += 1

    return succ, fail


def main() -> None:
    load_dotenv()
    outline_url = env("OUTLINE_URL", required=True)
    api_key = env("OUTLINE_API_KEY", required=True)
    source = env("SOURCE_FOLDER", required=True)
    name = env("OUTLINE_COLLECTION_NAME", "dynalist")
    req_delay = float(env("REQ_DELAY", "5.0"))

    if not os.path.isdir(source):
        print(f"ERROR: SOURCE_FOLDER not found: {source}", file=sys.stderr)
        sys.exit(1)

    api = Outline(outline_url, api_key, req_delay)
    auth = api.auth_info()
    if not auth.get("ok"):
        print(f"ERROR: auth failed: {auth}", file=sys.stderr)
        sys.exit(1)
    user = auth["data"]["user"]
    print(f"Authenticated as {user.get('name')} <{user.get('email')}>")

    collection_id = api.find_or_create_collection(name)
    print(f"Source folder: {source}")
    print(f"Request spacing: {req_delay}s\n")

    s, f = walk(api, collection_id, source, None, 0)
    print(f"\nDone: {s} created, {f} failed")
    sys.exit(0 if f == 0 else 1)


if __name__ == "__main__":
    main()
