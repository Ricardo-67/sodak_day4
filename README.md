# Hostel Complaints Desk: a sample end-to-end agent project

SoDak EduTech, Agentic AI Track, Day 4. This is the worked example for the weekend project: a
small, complete agent service.

A student asks a question in plain English. A **supervisor** agent delegates to two **specialist**
agents, an information specialist that can only look and a desk specialist that can raise complaints and
send texts. The run is a job on a queue, and a worker that dies halfway through doesn't raise the
complaint twice.

```text
student ─▶ queue (agent.db) ─▶ worker ─▶ supervisor ──ask_information──▶ information agent ─▶ get_room_by_number, find_complaint
                                                   └─ask_desk──────────▶ desk agent ────────▶ get_student, check_can_raise,
                                                                                              raise_complaint*, notify_student*
                                                                           * side effects: run once per key
```

## Run it (no API key needed)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.demo            # questions, scripted models, every step printed
python -m scripts.demo --crash    # the worker dies right after raising a complaint; a second worker finishes: PASS
pytest                            # tests
```

With Gemini (`export GEMINI_API_KEY=...`):

```bash
python -m scripts.demo --real                                      # same questions, real models
python -m scripts.worker                                           # terminal 1
python -m scripts.ask --student 22CS045 "Can you raise a plumbing complaint?"   # terminal 2
```

One question costs about 5–7 model calls with three agents, so the free tier runs out quickly.
Use the scripted models for everything except a final check.

## Where each day shows up

| Day | Idea | Where to look |
|---|---|---|
| 1 | The agent loop, self-healing tool errors | `app/agents.py` `run_specialist` |
| 2 | Tool descriptions are prompts; rules live in data; schema | `app/tools/hostel_tools.py`, `schema/hostel.sql` (`policy` table) |
| 2 | Agent memory apart from business data | `agent.db` vs `hostel.db` |
| 3 | A run is a job: queue, lease, heartbeat, reaper | `app/memory.py`, `app/worker.py`, `app/runner.py` |
| 3 | Idempotency keys; safe writes | `HostelDb.once`, `HostelDb.raise_complaint`, `record_notification` |
| 4 | Supervisor and specialists ("agent as tool") | `app/agents.py` `SupervisorTools` |
| 4 | Least privilege per agent | information has no write tools; `DeskTools` is bound to one roll number |
| 4 | Keys passed down to specialists | `run_tool` hands the delegation's key to `run_specialist` |

## Seed data

| Student | Warnings | Max warnings | What happens |
|---|---|---|---|
| 22CS045 Priya Raman | 0 | 2 | Can raise complaints |
| 22IT017 Arjun Kumar | 3 | 2 | Refused: warnings above the 2 max policy limit |
| 22EC031 Divya Sekar | 0 | 2 | Can raise complaints |

Rooms: A-101 (has an open electrical issue), A-102, B-201, B-202.

## Known limits (on purpose, for later days)

- A specialist's inner steps are not stored; only the delegation and its answer are. After a crash the
  specialist runs again, and keys keep its side effects single. Storing them is checkpointing (Day 5).
- Keys only match if the model repeats the same call. The scripted models always do; real models
  usually do at temperature 0. The side effects are also safe to repeat on their own, which
  covers the rest.
- No approval step before a side effect (Day 5), no guardrails or metrics (Day 6), no MCP (Day 7).
