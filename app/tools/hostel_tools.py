"""The hostel's tools, split between two specialist agents. Descriptions are prompts (Day 2)."""
from datetime import datetime, timezone

from app.idempotency import notification_dedupe_key
from app.hostel_db import HostelDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()     # run through HostelDb.once with an idempotency key (Day 3)
    DELEGATES: tuple[str, ...] = ()        # hand work to another agent (Day 4)
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class InformationTools(Toolset):
    """Read-only. The information agent can look, never change."""

    TOOL_NAMES = ("get_room", "find_complaint")

    def __init__(self, db: HostelDb):
        self.db = db

    def get_room(self, block: str, number: str) -> dict:
        """Get the details of a room in the hostel.
        
        Use to verify if a room exists. Read-only: changes nothing.

        Args:
            block: The block letter, e.g. "A" or "B".
            number: The room number string, e.g. "101".
            
        Returns:
            {"room_id", "block", "number"} or an error.
        """
        r = self.db.get_room_by_number(block, number)
        if not r:
            return {"error": "unknown_room", "hint": "The room does not exist."}
        return {"room_id": r["id"], "block": r["block"], "number": r["number"]}

    def find_complaint(self, block: str, number: str, issue: str = None) -> dict:
        """Find complaints for a specific room.
        
        Use for "what are the complaints in A 101" or "is there a plumbing issue in B 202". Read-only.
        
        Args:
            block: The block letter.
            number: The room number.
            issue: Optional word or phrase to filter complaints.
            
        Returns:
            {"complaints": [{"complaint_id", "issue", "status", "warden_assigned"}]}.
        """
        complaints = self.db.find_complaint(block, number, issue)
        return {"complaints": [{"complaint_id": c["id"], "issue": c["issue"], "status": c["status"], 
                                "warden_assigned": c["warden_assigned"]} for c in complaints]}


class DeskTools(Toolset):
    """The hostel desk, bound to ONE student. The model cannot pick a different roll number."""

    TOOL_NAMES = ("get_student", "check_can_raise", "raise_complaint", "assign_warden", "notify_student")
    SIDE_EFFECTS = ("raise_complaint", "assign_warden", "notify_student")

    def __init__(self, db: HostelDb, roll_no: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.roll_no, self.clock = db, roll_no, clock

    def _student(self) -> dict:
        s = self.db.get_student(self.roll_no)
        if s is None:
            raise LookupError(f"student {self.roll_no} not found")
        return s

    def get_student(self) -> dict:
        """Get the current student's record: name, room, and warnings.

        Use for "what is my room" or "how many warnings do I have". Read-only.

        Returns:
            {"roll_no", "name", "block", "number", "warnings"}.
        """
        s = self._student()
        return {"roll_no": s["roll_no"], "name": s["name"], "block": s.get("block"), 
                "number": s.get("number"), "warnings": s["warnings"]}

    def check_can_raise(self) -> dict:
        """Decide whether the current student can raise a complaint, using the hostel policy.

        Use BEFORE raise_complaint. Read-only.

        Returns:
            {"can_raise": bool, "reasons": [str]}.
        """
        s = self._student()
        reasons = []
        limit = self.db.policy("max_warnings")
        if s["warnings"] > limit:
            reasons.append(f"warnings count {s['warnings']} is above the {limit} limit")
        return {"can_raise": not reasons, "reasons": reasons}

    def raise_complaint(self, issue: str) -> dict:
        """Raise a new complaint for the student's room. CHANGES DATA.

        Use only when the student asked to raise an issue and check_can_raise allowed it.
        
        Args:
            issue: Short description of the issue.

        Returns:
            {"status": "raised" | "already_raised"} or an error.
        """
        verdict = self.check_can_raise()
        if not verdict["can_raise"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"],
                    "hint": "Explain the reasons to the student. Do not retry."}
        s = self._student()
        if not s.get("room_id"):
            return {"error": "no_room", "hint": "The student has no room assigned."}
        status = self.db.raise_complaint(s["room_id"], issue)
        return {"status": status, "issue": issue}

    def assign_warden(self, complaint_id: int, warden: str) -> dict:
        """Assign a warden to a specific complaint. CHANGES DATA.
        
        Args:
            complaint_id: Integer id of the complaint.
            warden: Name of the warden.
            
        Returns:
            {"status": "assigned" | "not_found_or_closed"}.
        """
        status = self.db.assign_warden(complaint_id, warden)
        return {"status": status, "complaint_id": complaint_id, "warden": warden}

    def notify_student(self, message: str) -> dict:
        """Send the current student a short text message. CHANGES DATA.

        Use to confirm something that just happened.

        Args:
            message: 1 to 160 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "message must be 1 to 160 characters."}
        key = notification_dedupe_key(self.roll_no, message, self.clock().date())
        notification_id, created = self.db.record_notification(self.roll_no, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}
