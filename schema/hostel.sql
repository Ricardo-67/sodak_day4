-- hostel.db: the hostel's own data. The agent's memory is in agent.db.

CREATE TABLE IF NOT EXISTS room (
    id         INTEGER PRIMARY KEY,
    block      TEXT NOT NULL,
    number     TEXT NOT NULL,
    UNIQUE (block, number)
);

CREATE TABLE IF NOT EXISTS student (
    id         INTEGER PRIMARY KEY,
    roll_no    TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    room_id    INTEGER REFERENCES room (id),
    warnings   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS complaint (
    id                INTEGER PRIMARY KEY,
    room_id           INTEGER NOT NULL REFERENCES room (id),
    issue             TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'open',  -- 'open', 'resolved'
    warden_assigned   TEXT,
    created_at        REAL NOT NULL
);

-- Business rule in data: one open complaint per room per issue.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_issue ON complaint (room_id, issue) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Day 3: keys live next to the side effects they guard.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
