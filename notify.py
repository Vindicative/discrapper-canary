import json
import os
import re
import urllib.parse
import urllib.request

UPSTREAM = os.environ.get("UPSTREAM", "Wumpus-Central/discrapper-canary")
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
    # hits the GitHub API and hands back the json
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
    # shoots stuff over to Discord
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "discrapper-sync"},
    )
    urllib.request.urlopen(req)


def find_build(commits):
    # hunts for the build number in the commit messages
    for c in reversed(commits):
        m = re.search(r"\b(\d{5,7})\b", c["commit"]["message"])
        if m:
            return m.group(1)
    return NEW[:7]


def block(text, lang="diff"):
    return f"```{lang}\n{text}\n```"


def commits_text(commits):
    # what the devs said in their commits, newest on top
    lines, size = [], 0
    ordered = list(reversed(commits))
    for i, c in enumerate(ordered):
        msg = c["commit"]["message"].split("\n")[0][:80]
        who = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
        line = f"[`{c['sha'][:7]}`]({c['html_url']}) {msg} - **{who}**"
        if size + len(line) > 900:
            lines.append(f"...and {len(ordered) - i} more")
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines) or "No commit messages, they left us on read"


def load_strings(sha):
    # grabs the strings file from upstream at a specific commit
    path = urllib.parse.quote(STRINGS_PATH)
    url = f"https://api.github.com/repos/{UPSTREAM}/contents/{path}?ref={sha}"
    try:
        return gh(url, accept="application/vnd.github.raw+json")
    except Exception as e:
        print(f"Couldn't grab the strings at {sha[:7]}: {e}")
        return {}


def send_strings(title, lines, build, state):
    if not lines:
        return
    # chop it up so Discord doesn't throw a fit about the size limit
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
        # only ping the role once, on the first message, no one likes spam
        if ROLE_ID and not state["mentioned"]:
            payload["content"] = f"<@&{ROLE_ID}>"
            payload["allowed_mentions"] = {"roles": [ROLE_ID]}
            state["mentioned"] = True
        post(payload)


cmp = gh(f"https://api.github.com/repos/{UPSTREAM}/compare/{OLD}...{NEW}")
files = cmp.get("files", [])
commits = cmp.get("commits", [])
build = find_build(commits)

added_lines = sum(f.get("additions", 0) for f in files)
removed_lines = sum(f.get("deletions", 0) for f in files)
chunks_added = sum(1 for f in files if f["status"] == "added")
chunks_removed = sum(1 for f in files if f["status"] == "removed")
chunks_changed = len(files) - chunks_added - chunks_removed

diff_url = cmp.get("html_url", f"https://github.com/{UPSTREAM}/commits/main")

post(
    {
        "embeds": [
            {
                "color": AMBER,
                "fields": [
                    {"name": "Build", "value": block(build, ""), "inline": True},
                    {"name": "Lines Added", "value": block(f"+ {added_lines}"), "inline": True},
                    {"name": "Lines Yeeted", "value": block(f"- {removed_lines}"), "inline": True},
                    {"name": "[++] New Files", "value": block(f"+ {chunks_added}"), "inline": True},
                    {"name": "[+-] Tweaked Files", "value": block(f"* {chunks_changed}"), "inline": True},
                    {"name": "[--] Deleted Files", "value": block(f"- {chunks_removed}"), "inline": True},
                    {"name": "💬 What The Devs Said", "value": commits_text(commits), "inline": False},
                    {"name": "\u200b", "value": f"[Check out the diff]({diff_url})", "inline": False},
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
    send_strings("(++) FRESH STRINGS", added, build, state)
    send_strings("(-+) TWEAKED STRINGS", updated, build, state)
    send_strings("(--) YEETED STRINGS", removed, build, state)
