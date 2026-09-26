#!/usr/bin/env python3
"""One-shot migration: legacy file-based todos -> SQLite.

Reads ~/.openclaw/state/todos/YYYY-MM-DD.md (Markdown checkbox list),
inserts items into the todos DB. Idempotent per (created_day, description):
re-running will not duplicate rows it already inserted.

Usage:
    python3 migrate_todo_md.py [--db PATH] [--dir ~/.openclaw/state/todos]

After a successful run the legacy .md files are moved to
~/.openclaw/state/todos/legacy/ (not deleted).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from zoneinfo import ZoneInfo

_TODO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo")
_t = SourceFileLoader("todo", _TODO).load_module()
SCHEMA = _t.SCHEMA
DEFAULT_DB = _t.DEFAULT_DB
MAX_DESC = _t.MAX_DESC
STATE_DONE = _t.STATE_DONE
STATE_PENDING = _t.STATE_PENDING
TZ = _t.TZ

ITEM_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$")
DAY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def parse_file(path: str) -> tuple[str, list[tuple[str, str]]]:
    day = DAY_RE.match(os.path.basename(path)).group(1)
    items: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = ITEM_RE.match(line)
            if not m:
                continue
            state = STATE_DONE if m.group(1).lower() == "x" else STATE_PENDING
            desc = m.group(2).strip()[:MAX_DESC]
            items.append((state, desc))
    return day, items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dir", default=os.path.expanduser("~/.openclaw/state/todos"))
    ap.add_argument("--no-archive", action="store_true", help="Leave legacy files in place")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")

    files = sorted(
        os.path.join(args.dir, f)
        for f in os.listdir(args.dir)
        if DAY_RE.match(f)
    )
    if not files:
        print(f"no legacy YYYY-MM-DD.md files found in {args.dir}")
        return 0

    total_inserted = 0
    for path in files:
        day, items = parse_file(path)
        inserted = 0
        for state, desc in items:
            exists = conn.execute(
                "SELECT id FROM todos WHERE created_day = ? AND description = ?", (day, desc)
            ).fetchone()
            if exists:
                continue
            order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM todos WHERE created_day = ?", (day,)
            ).fetchone()["n"]
            conn.execute(
                "INSERT INTO todos (created_day, state, description, sort_order, created_at) "
                "VALUES (?,?,?,?,?)",
                (day, state, desc, order, now),
            )
            inserted += 1
        conn.commit()
        total_inserted += inserted
        print(f"{os.path.basename(path)}: parsed {len(items)} item(s), inserted {inserted}")

    print(f"total inserted: {total_inserted}")

    if not args.no_archive:
        archive = os.path.join(args.dir, "legacy")
        os.makedirs(archive, exist_ok=True)
        for path in files:
            shutil.move(path, os.path.join(archive, os.path.basename(path)))
        print(f"archived {len(files)} legacy file(s) -> {archive}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
