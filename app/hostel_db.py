"""hostel.db: rooms, students, complaints. Every SQL statement for the hostel lives here."""
import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "hostel.sql"


class HostelDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM student").fetchone()[0]:
            return
        with self.transaction() as c:
            # Insert rooms
            c.executemany("INSERT INTO room VALUES (?, ?, ?)", [
                (1, "A", "101"),
                (2, "A", "102"),
                (3, "B", "201"),
                (4, "B", "202")
            ])
            # Insert students
            c.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", 1, 0),
                (2, "22IT017", "Arjun Kumar", 2, 3), # 3 warnings, cannot raise more complaints
                (3, "22EC031", "Divya Sekar", 4, 0)
            ])
            # Insert policy
            c.executemany("INSERT INTO policy VALUES (?, ?)", [("max_warnings", 2)])
            
            # Seed a complaint (A-101 has an open electrical issue)
            c.execute("INSERT INTO complaint (room_id, issue, created_at) VALUES (?, ?, ?)",
                      (1, "electrical", self.clock()))

    # ------------------------------------------------------------------ reads

    def get_student(self, roll_no: str) -> dict | None:
        r = self.conn.execute(
            "SELECT s.*, r.block, r.number FROM student s LEFT JOIN room r ON r.id = s.room_id WHERE s.roll_no = ?",
            (roll_no,)
        ).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        return self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()[0]

    def get_room_by_number(self, block: str, number: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM room WHERE block = ? AND number = ?", (block, number)).fetchone()
        return dict(r) if r else None

    def find_complaint(self, block: str, number: str, issue: str = None) -> list[dict]:
        room = self.get_room_by_number(block, number)
        if not room:
            return []
        
        query = "SELECT * FROM complaint WHERE room_id = ?"
        params = [room["id"]]
        if issue:
            query += " AND issue LIKE ?"
            params.append(f"%{issue.strip()}%")
        query += " ORDER BY id DESC"
        
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes (Day 3)

    def raise_complaint(self, room_id: int, issue: str) -> str:
        """Returns 'raised' or 'already_raised'."""
        with self.transaction() as c:
            try:
                c.execute("INSERT INTO complaint (room_id, issue, created_at) VALUES (?, ?, ?)",
                          (room_id, issue, self.clock()))
                return "raised"
            except sqlite3.IntegrityError:
                # The unique index prevents duplicate open issues per room
                return "already_raised"

    def assign_warden(self, complaint_id: int, warden: str) -> str:
        """Returns 'assigned' or 'not_found'."""
        with self.transaction() as c:
            took = c.execute("UPDATE complaint SET warden_assigned = ? WHERE id = ? AND status = 'open'",
                             (warden, complaint_id)).rowcount
            if not took:
                return "not_found_or_closed"
            return "assigned"

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT INTO notification (roll_no, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (roll_no, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key = ?", (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key; the effect and its key commit together."""
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
