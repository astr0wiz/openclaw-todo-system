# STATUS.md — Todo List System

**Status:** ✅ v1 complete and live (2026-09-25)
**Location:** `~/dev/prj/openclaw/todo-system`
**Owner:** Jamie Jensen

## What it is

A persistent, SQLite-backed daily todo list that survives sessions, renders a
combined "today + still-pending older days" view, reminds on a schedule, and can
be driven either from a shell or in natural language through the OpenClaw agent.

## Layout

| Path | Purpose |
| --- | --- |
| `~/dev/prj/openclaw/todo-system/todo` | Python 3 CLI (no third-party deps) |
| `~/dev/prj/openclaw/todo-system/migrate_todo_md.py` | One-shot legacy Markdown → SQLite migration |
| `~/dev/prj/openclaw/todo-system/STATUS.md` | This file |
| `~/.openclaw/state/todos/todos.db` | Runtime database (SQLite) |
| `~/.openclaw/state/todos/legacy/` | Archived pre-SQLite `YYYY-MM-DD.md` files |

The DB is deliberately kept out of the project dir: the project is code + docs,
the state directory is OpenClaw's runtime state.

## Data model

```sql
CREATE TABLE todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_day  TEXT NOT NULL,                 -- YYYY-MM-DD (America/Chicago)
    state        TEXT NOT NULL DEFAULT 'not-done'
                 CHECK (state IN ('not-done', 'done')),
    description  TEXT NOT NULL
                 CHECK (length(description) BETWEEN 1 AND 120),
    sort_order   INTEGER NOT NULL DEFAULT 0,    -- stable creation order within a day
    created_at   TEXT NOT NULL                  -- ISO-8601 local timestamp
);
```

`sort_order` (not `id`) is the primary display order within a day, so imported
items keep their original order.

## Display format

```
Today's list (2026-09-25):
1. [x] Phone call from recruiter
2. [ ] Brainstorm new Grognard articles

Days Aged: 2
1. [ ] Something from Tuesday

Days Aged: 5
1. [ ] Something from Sunday
```

- Every item is rendered as a Markdown-style checkbox + description.
- Today's section shows **all** items for the current day, any state.
- Older sections show **only still-`not-done`** items, grouped by age.
- The heading is *Days Aged* (integer days between creation and today),
  ordered **most recent group first**.
- Numbering restarts within each group for readability, but **commands accept
  one continuous running number across groups** (today first, then aged groups
  newest→oldest), exactly matching top-to-bottom reading order. The CLI resolves
  the live numbering at the moment the command runs.

## CLI

```
./todo list                    # render the list (alias: show)
./todo add "text" ["text"...]  # add item(s) to today
./todo init "a" "b"            # create today's list; refuses if today is non-empty
./todo init "a" --force        # replace today's list
./todo done 2 4                # mark displayed #2 and #4 done
./todo undone 3                # revert to not-done
./todo rm 1                    # remove displayed #1 (alias: remove)
./todo clear --yes             # delete every item for the reference day
```

Global flags: `--db PATH` (default `~/.openclaw/state/todos/todos.db`).
Subcommand flag: `--day YYYY-MM-DD` to operate on a non-today day.
Env: `TODO_DB`, `TODO_TZ` (default `America/Chicago`).

Exit codes: `0` ok, `1` sqlite error, `2` bad item number.

## Agent / natural-language interface

The agent maps chat requests onto the CLI. Canonical phrasings:

- **"initiate a todo list"** → create today's list.
  - If today already has items: ask whether to delete them first; delete only on
    an affirmative reply, then ask for items **one at a time**.
  - If today is empty: go straight to asking for items one at a time.
  - "done" / "that's it" / "no more" ends initialization.
  - Each item is persisted as it is supplied.
- **"show my todo list"** → run `./todo list` and return the output verbatim.
- **add / remove / change state** → `todo add|rm|done|undone`, then always
  re-render the list so the change can be verified.

## Automation

| Field | Value |
| --- | --- |
| Name | `todo-reminders` |
| Job id | `86de4caa-bd2d-423d-a65e-db1a1790c9a2` |
| Schedule | `0 6,12,18 * * *` @ America/Chicago (exact, no stagger) |
| Payload | `command`: `~/dev/prj/openclaw/todo-system/todo list` |
| Delivery | announce → telegram:7560164654, best-effort |

### How the three daily runs are used

The three runs are not identical in purpose:

- **6:00 am — the anchor.** Jamie will typically *initiate a new list* right after
  seeing this display: "initiate a todo list" followed by items one at a time (see
  the agent interface above). The 6 am view is therefore both the previous day's
  leftover check and the cue to set up today's list.
- **12:00 pm — midday reminder.** A check-in on progress; no list creation expected.
- **6:00 pm — end-of-day reminder.** A closing look at what is still outstanding.

Items get completed *during* the day, not at reminder time: Jamie interacts via
chat to modify the list (mark done/undone, add, remove) as work happens, and each
change re-renders the list for verification. The reminders are read-only — they
never mutate the list and never prompt.

Retired: the previous file-based job `today-todo-reminders`
(`441569a5-98af-40ea-b712-2f2cdd19f01d`, hourly 9am–5pm) was removed after the
migration. A one-shot cleanup job referenced in the old Markdown file
(`27450d70-…`, `today-todo-cleanup`, 17:01 CT) was not present in the automation
list at retirement time.

## Migration log

- 2026-09-25: `migrate_todo_md.py` parsed `2026-09-25.md`, inserted 5 items
  (4 done, 1 pending: "Brainstorm new Grognard articles"), and moved the file to
  `~/.openclaw/state/todos/legacy/`. Verified by `./todo list`.
- Migration is idempotent per `(created_day, description)`.

## Verification performed

- CLI smoke tests: add / done / undone / rm / init on a temp DB.
- Aged grouping: items from 09-20 and 09-23 rendered as `Days Aged: 5` then `2`.
- Cross-group numbering: `done 3` correctly hit the oldest group.
- Migration output checked against the source Markdown (5/5 items, states intact).
- Automation test-fired; delivery reported `delivered`, payload matched the
  expected render.

## Known limits / next steps

- Deleting an old not-done item frees its number for the next item; always
  re-render after a change (the CLI does this) before issuing another numbered
  command.
- No edit-in-place for descriptions (`rm` + `add` is the workaround).
- No per-item reminders or priorities — not requested.
- Git init/push intentionally left to Jamie (done offline after this session).

## Restore / rollback

Old behavior is recoverable: legacy Markdown files are intact under
`~/.openclaw/state/todos/legacy/`, and the DB can be rebuilt by re-running
`migrate_todo_md.py`. Recreating the hourly job is a one-liner if ever needed.
