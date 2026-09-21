"""Day 4: three agents. A supervisor talks to the student and delegates to two specialists.

    student ──▶ supervisor ──ask_information──▶ information agent (get_room, find_complaint)
                           └─ask_desk───────▶ desk agent        (get_student, check_can_raise,
                                                                 raise_complaint, assign_warden, notify_student)

Each specialist is an ordinary agent loop with its own system prompt and its own small tool set.
To the supervisor, a specialist is just a tool: "agent as tool", the simplest multi-agent pattern.
"""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.hostel_db import HostelDb
from app.providers import AgentError
from app.tools.hostel_tools import InformationTools, DeskTools, Toolset

SPECIALIST_MAX_STEPS = 6

SUPERVISOR_SYSTEM = """You are the Hostel Complaints Desk Assistant, talking to the student with roll number {roll_no}.
You never look up rooms or change complaints yourself. Delegate:
- ask_information for finding rooms and past complaints;
- ask_desk for anything about this student's record, raising complaints, assigning wardens, or sending messages.
Give each specialist a complete, specific request.
Then answer the student briefly, using only what the specialists reported."""

INFORMATION_SYSTEM = """You are the information specialist of a hostel. Find rooms and complaints and report
their details. You cannot raise complaints or change anything. Be brief."""

DESK_SYSTEM = """You are the complaints desk specialist, acting for student {roll_no} only.
Always call check_can_raise before raise_complaint. Never decide policy yourself: report the reasons
the tools give. Confirm a successful complaint with notify_student. Report what you did, briefly."""


def run_tool(toolset: Toolset, db: HostelDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    """Run one tool call for any agent. Returns (result, replayed). Never raises, except AgentError.

    Side effects run at most once per key (Day 3); replayed is True when the stored result was returned
    and nothing was done. Delegations hand the key down, so the specialist's side effects get keys
    derived from it: a replayed delegation replays its side effects safely too.
    """
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet."}, False
    except Exception as e:
        print(f"DEBUG: tool {name} failed with {type(e).__name__}: {e}")
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: HostelDb, provider, task: str,
                   parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    """A specialist's whole agent loop, run inside one tool call of the supervisor."""
    contents = [{"role": "user", "text": task}]
    functions = list(toolset.functions().values())
    used = []
    seq = 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, functions)
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            key = idempotency_key(parent_key, seq, call.name, call.args)
            started = time.perf_counter()
            result, replayed = run_tool(toolset, db, key, call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args, "result": result,
                         "ok": "error" not in result, "replayed": replayed,
                         "ms": round((time.perf_counter() - started) * 1000)})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used,
            "hint": "The specialist could not finish. Tell the student to try a simpler request."}


class SupervisorTools(Toolset):
    """The supervisor's only tools are the two specialists."""

    TOOL_NAMES = ("ask_information", "ask_desk")
    DELEGATES = ("ask_information", "ask_desk")

    def __init__(self, db: HostelDb, providers: dict, roll_no: str, on_step=None):
        self.db, self.providers, self.roll_no, self.on_step = db, providers, roll_no, on_step

    def ask_information(self, question: str) -> dict:
        """Ask the information specialist to find rooms or complaints.

        Use for "what are the complaints in A 101" or "is there a plumbing issue in B 202". It cannot change data.

        Args:
            question: A complete request, e.g. "What are the open complaints in room A 101?"

        Returns:
            {"agent": "information", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def ask_desk(self, request: str) -> dict:
        """Ask the complaints desk specialist to act on this student's record. It CAN CHANGE DATA:
        raise complaints, assign wardens, and send the student messages.

        Use for raising complaints, "how many warnings do I have", and confirmations.
        The desk always acts for the current student only.

        Args:
            request: A complete instruction, e.g. "Raise a plumbing complaint and text the student."

        Returns:
            {"agent": "desk", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        bad = self.call_check(name, args)
        if bad:
            return bad
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_information":
            return run_specialist("information", INFORMATION_SYSTEM, InformationTools(self.db), db=self.db,
                                  provider=self.providers["information"], task=args["question"],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("desk", DESK_SYSTEM.format(roll_no=self.roll_no), DeskTools(self.db, self.roll_no),
                              db=self.db, provider=self.providers["desk"], task=args["request"],
                              parent_key=key, on_step=self.on_step)

    def call_check(self, name: str, args: dict) -> dict | None:
        """Validate a delegation's arguments the same way dispatch validates any tool call."""
        field = "question" if name == "ask_information" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string: {field}."}
        return None
