import json
import os
import re
import urllib.parse
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
UPSTREAM = "Wumpus-Central/discrapper-canary"
OLD = os.environ["OLD"]
NEW = os.environ["NEW"]
WEBHOOK = os.environ["WEBHOOK"]
TOKEN = os.environ["GH_TOKEN"]
STRINGS_PATH = os.environ.get("STRINGS_PATH", "").strip()
ROLE_ID = os.environ.get("STRINGS_ROLE_ID", "").strip()

AMBER = 0xF5B921
BLURPLE = 0x5865F2
AVATAR = "https://github.com/Wumpus-Central.png"


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


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "discrapper-sync"},
    )
    urllib.request.urlopen(req)


def exists(url):
    try:
        gh(url)
        return True
    except Exception:
        return False


def find_build(commits):
    for c in reversed(commits):
        m = re.search(r"\b(\d{5,7})\b", c["commit"]["message"])
        if m:
            return m.group(1)
    return NEW[:7]


def block(text, lang="diff"):
    return f"```{lang}\n{text}\n```"


def load_strings(sha):
    path = urllib.parse.quote(STRINGS_PATH)
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={sha}"
    try:
        return gh(url, accept="application/vnd.github.raw+json")
    except Exception as e:
        print(f"Could not load strings at {sha[:7]}: {e}")
        return {}


def send_strings(title, lines, build, state):
    if not lines:
        return
    chunks, chunk, size = [], [], 0
    for line in lines:
        line = line[:500].replace("```", "'''")
        if size + len(line) + 1 > 3500:
            chunks.append(chunk)
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        chunks.append(chunk)

    for part in chunks:
        payload = {
            "embeds": [
                {
                    "author": {
                        "name": "discrapper-canary",
                        "icon_url": AVATAR,
                        "url": f"https://github.com/{UPSTREAM}",
                    },
                    "description": f"- {title}\n" + block("\n".join(part)),
                    "color": BLURPLE,
                    "footer": {"text": f"Build Id - {build}"},
                }
            ]
        }
        if ROLE_ID and not state["mentioned"]:
            payload["content"] = f"<@&{ROLE_ID}>"
            payload["allowed_mentions"] = {"roles": [ROLE_ID]}
            state["mentioned"] = True
        post(payload)


cmp = gh(f"https://api.github.com/repos/{REPO}/compare/{OLD}...{NEW}")
files = cmp.get("files", [])
build = find_build(cmp.get("commits", []))

added_lines = sum(f.get("additions", 0) for f in files)
removed_lines = sum(f.get("deletions", 0) for f in files)
chunks_added = sum(1 for f in files if f["status"] == "added")
chunks_removed = sum(1 for f in files if f["status"] == "removed")
chunks_changed = len(files) - chunks_added - chunks_removed

upstream_cmp = f"https://github.com/{UPSTREAM}/compare/{OLD}...{NEW}"
diff_url = (
    upstream_cmp
    if exists(f"https://api.github.com/repos/{UPSTREAM}/compare/{OLD}...{NEW}")
    else cmp.get("html_url", f"https://github.com/{UPSTREAM}/commits/main")
)

post(
    {
        "embeds": [
            {
                "color": AMBER,
                "fields": [
                    {"name": "Release", "value": block(build, ""), "inline": True},
                    {"name": "Added Lines", "value": block(f"+ {added_lines}"), "inline": True},
                    {"name": "Removed Lines", "value": block(f"- {removed_lines}"), "inline": True},
                    {"name": "[++] Chunks", "value": block(f"+ {chunks_added}"), "inline": True},
                    {"name": "[+-] Chunks", "value": block(f"* {chunks_changed}"), "inline": True},
                    {"name": "[--] Chunks", "value": block(f"- {chunks_removed}"), "inline": True},
                    {"name": "\u200b", "value": f"[View Differences]({diff_url})", "inline": False},
                ],
            }
        ]
    }
)

if STRINGS_PATH:
    a, b = load_strings(OLD), load_strings(NEW)
    added = [f"+ {k}: {v}" for k, v in b.items() if k not in a]
    removed = [f"- {k}: {v}" for k, v in a.items() if k not in b]
    updated = []
    for k in a.keys() & b.keys():
        if a[k] != b[k]:
            updated += [f"- {k}: {a[k]}", f"+ {k}: {b[k]}"]
    state = {"mentioned": False}
    send_strings("(++) ADDED", added, build, state)
    send_strings("(-+) UPDATED", updated, build, state)
    send_strings("(--) REMOVED", removed, build, state)
