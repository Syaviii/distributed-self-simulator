"""Pull sworn branch oaths out of a Discord channel and write them as CSV.

The oath is worth 2 merit and is half the gate on advancing past Group
Loyalist, so the oath channel is the cheapest place to start backdating. The
output feeds straight into import_merit.py.

    export DISCORD_TOKEN=...
    python tools/scrape_oaths.py 1502579575970861087 > oaths.csv
    python tools/import_merit.py oaths.csv

One row per member, earliest oath kept, so someone who swore twice counts once.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
DEFAULT_PATTERN = r"solemnly swear"


def context() -> ssl.SSLContext:
    """Honour a custom CA bundle, which corporate and proxied networks need."""
    bundle = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=bundle) if bundle else ssl.create_default_context()


def get(url: str, token: str) -> list[dict]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (abexilian-merit-bot, 0.1)",
        },
    )
    with urllib.request.urlopen(request, timeout=30, context=context()) as response:
        return json.load(response)


def fetch_messages(channel_id: str, token: str, limit: int) -> list[dict]:
    """Page backwards through a channel until it runs out or we hit the limit."""
    messages: list[dict] = []
    before: str | None = None
    while len(messages) < limit:
        batch = min(100, limit - len(messages))
        url = f"{API}/channels/{channel_id}/messages?limit={batch}"
        if before:
            url += f"&before={before}"
        page = get(url, token)
        if not page:
            break
        messages.extend(page)
        before = page[-1]["id"]
        if len(page) < batch:
            break
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("channel_id", help="channel holding the oaths")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="regex marking a message as an oath")
    parser.add_argument("--limit", type=int, default=1000, help="how many messages to read back")
    parser.add_argument("--merit", type=int, default=2, help="merit the oath is worth")
    args = parser.parse_args()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is not set.", file=sys.stderr)
        return 2

    try:
        messages = fetch_messages(args.channel_id, token, args.limit)
    except urllib.error.HTTPError as exc:
        print(f"Discord returned {exc.code} for channel {args.channel_id}.", file=sys.stderr)
        return 2

    pattern = re.compile(args.pattern, re.IGNORECASE)
    found: dict[str, dict] = {}
    for message in messages:
        if message.get("author", {}).get("bot"):
            continue
        if not pattern.search(message.get("content", "")):
            continue
        author = message["author"]
        # Messages arrive newest first, so later writes are the earlier oath.
        found[author["id"]] = {
            "user_id": author["id"],
            "name": author.get("global_name") or author["username"],
            "merit": args.merit,
            "oath": "yes",
            "note": f"Branch oath sworn {message['timestamp'][:10]}",
        }

    writer = csv.DictWriter(sys.stdout, fieldnames=["user_id", "name", "merit", "oath", "note"])
    writer.writeheader()
    for row in found.values():
        writer.writerow(row)

    print(f"{len(found)} oath(s) from {len(messages)} message(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
