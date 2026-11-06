import pandas as pd
import json
import numpy as np
from pathlib import Path
import argparse
import os
from dotenv import load_dotenv
_MISSING = object()

def get(d, *keys, default=None):
    if not keys:
        return d

    key, *remaining = keys
    if isinstance(d, dict):
        if key not in d:
            return default
        return get(d[key], *remaining, default=default)
    if isinstance(d, list):
        values = []
        for item in d:
            value = get(item, key, *remaining, default=_MISSING)
            if value is not _MISSING:
                values.append(value)
        return values
    return default


rows = []
load_dotenv()
for path in Path(os.environ.get("DATA_DIRECTORY")).glob("*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            m = json.loads(line)
            rows.append({
                "timestamp": m["timestamp"],
                "channel_id": m["channel_id"],
                "message_id": m["id"],
                "author_id": m["author"]["id"],
                "author_username": m["author"]["username"],
                "nickname": m["author"]["global_name"],
                "content": m["content"],
                "mentioned": get(m, "mentions", "username"),
                "attachments": get(m, "attachments", "filename"),
                "embed_title": get(m, "embeds", "title"),
                "embed_url": get(m, "embeds", "url"),
                "sticker": get(m, "sticker_items", "name"),
                "reaction_count": sum(get(m, "reactions", "count") or []),
                "reaction_emoji": get(m, "reactions", "emoji", "name")
            })



df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
df[["channel_id", "author_id", "author_username", "nickname"]] = df[["channel_id", "author_id", "author_username", "nickname"]].astype("category")
df = df.sort_values("timestamp", kind="stable", ignore_index=True)

df.info()
print(df.tail(10))
df

