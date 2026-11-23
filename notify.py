import json
import os
import urllib.parse
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
UPSTREAM = "Wumpus-Central/discrapper-canary"
OLD = os.environ["OLD"]
NEW = os.environ["NEW"]
WEBHOOK = os.environ["WEBHOOK"]
TOKEN = os.environ["GH_TOKEN"]
STRINGS_PATH = os.environ.get("STRINGS_PATH", "").strip()


def gh(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": accept,
            "User-Agent": "discrapper-sync",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def post(content):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps({"content": content}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "discrapper-sync"},
    )
    urllib.request.urlopen(req)


def send_block(title, lines):
    """Sends lines as a diff block, splitting if it exceeds Discord's 2000 character limit."""
    if not lines:
        return
    chunk, size = [], 0
    for line in lines:
        line = line[:500]
        if size + len(line) > 1700:
            post(f"{title}\n```diff\n" + "\n".join(chunk) + "\n```")
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        post(f"{title}\n```diff\n" + "\n".join(chunk) + "\n```")


def load_strings(sha):
    path = urllib.parse.quote(STRINGS_PATH)
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={sha}"
    try:
        return gh(url, accept="application/vnd.github.raw+json")
    except Exception as e:
        print(f"Could not load strings at {sha[:7]}: {e}")
        return {}


cmp = gh(f"https://api.github.com/repos/{REPO}/compare/{OLD}...{NEW}")
files = cmp.get("files", [])
summary = [
    f"**discrapper-canary** `{OLD[:7]}` → `{NEW[:7]}` ({len(files)} files)",
    f"https://github.com/{UPSTREAM}/commits/main",
]
post("\n".join(summary))

if STRINGS_PATH:
    a, b = load_strings(OLD), load_strings(NEW)
    added = [f"+ {k}: {v}" for k, v in b.items() if k not in a]
    removed = [f"- {k}: {v}" for k, v in a.items() if k not in b]
    updated = []
    for k in a.keys() & b.keys():
        if a[k] != b[k]:
            updated += [f"- {k}: {a[k]}", f"+ {k}: {b[k]}"]
    send_block("(++) ADDED", added)
    send_block("(-+) UPDATED", updated)
    send_block("(--) REMOVED", removed)
