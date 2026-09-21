# Hostel Complaints Desk: Workflow & Functionality

This project implements an end-to-end agentic AI service for a Hostel Complaints Desk. It relies on a multi-agent architecture to process student requests safely, idempotently, and durably.

## 1. Domain & Functionality

The service handles student complaints for hostel rooms. Students can interact with the service in plain English to:
- Look up room details.
- Find past or open complaints for a given room.
- Check their own record (room assignment and warning count).
- Raise a new complaint (e.g., plumbing, electrical).
- Assign a warden to an open complaint.
- Receive a notification confirming the action.

### Business Rules Enforced in Data
The core business rule is **"One open complaint per room per issue"**. This is strictly enforced in the SQLite database (`schema/hostel.sql`) using a `UNIQUE INDEX` constraint. Even if an agent erroneously attempts to raise a duplicate open issue, the database will block it, guaranteeing data integrity. 

Another rule limits students from raising complaints if they have too many warnings, checked by the `check_can_raise` tool.

---

## 2. Multi-Agent Architecture

The service uses a "Supervisor and Specialists" pattern (Agent-as-a-Tool).

### The Supervisor Agent
When a student submits a request, it is routed to the **Supervisor**. The supervisor's system prompt prevents it from directly accessing the database or modifying data. Instead, it parses the student's intent and delegates tasks to two specialists.

### Specialist 1: Information Agent (Read-Only)
- **Role:** Handles lookups and verification without any risk of changing data.
- **Tools Available:**
  - `get_room`: Verifies if a room exists and retrieves its details.
  - `find_complaint`: Searches for past or current complaints in a specific room.

### Specialist 2: Desk Agent (Read/Write)
- **Role:** Handles actions that modify the database (side-effects) and checks student-specific records. This agent acts *only* on behalf of the specific student making the request.
- **Tools Available:**
  - `get_student`: Retrieves the student's record and warning count.
  - `check_can_raise`: Evaluates the hostel policy to confirm the student is allowed to raise a complaint.
  - `raise_complaint`: Inserts a new complaint into the database (Side Effect).
  - `assign_warden`: Assigns a warden to an open complaint (Side Effect).
  - `notify_student`: Sends a text notification to the student (Side Effect).

---

## 3. Workflow Example

When a student (`22CS045`) says: *"I need to raise a plumbing complaint in my room and please text me."*

1. **Queueing:** The request is saved to `agent.db` as a new run in a conversation thread.
2. **Worker Claim:** A background worker claims the run with a time-bound lease.
3. **Supervisor Delegation:** The worker invokes the Supervisor, which decides to use the `ask_desk` tool with the instruction: *"Raise a plumbing complaint and text the student to confirm."*
4. **Specialist Execution:** The Desk Agent takes over.
   - It calls `check_can_raise` to ensure the student isn't blocked by warnings.
   - It calls `raise_complaint({"issue": "plumbing"})`. The data layer securely commits the complaint.
   - It calls `notify_student` to send the confirmation.
5. **Supervisor Response:** The Desk Agent reports success back to the Supervisor, which formulates the final plain-English reply to the student.
6. **Completion:** The worker marks the run as `succeeded` and stores the final message.

---

## 4. Durability & Idempotency

Agent workflows are unpredictable and background workers can crash at any time. This project guarantees safety through two mechanisms:

### The Queue & Lease System
Requests are not processed synchronously. They are added to a queue (`agent.db`). A worker takes a "lease" on the job. If the worker crashes (e.g., power failure mid-run), the lease eventually expires. Another worker will notice the expired lease and pick up the job where it left off, ensuring no request is ever permanently dropped.

### Idempotency Keys
Because a crashed job will be retried by a new worker, the agents might attempt to perform the same side-effect twice (e.g., raising the same complaint or sending the same notification). 
To prevent this, every side-effect tool generates a deterministic **Idempotency Key**. 
- When `raise_complaint` is executed, its result is saved alongside its key in the `idempotency` table in the exact same transaction.
- When the new worker retries the job and calls `raise_complaint` again, the database sees the existing key, intercepts the action, and simply replays the *stored result* without actually inserting a duplicate complaint.

---

## 5. How to Run

1. **Demo with Scripted Models (No API Key Required):**
   ```bash
   python -m scripts.demo
   ```
   Runs a full simulation demonstrating successful and rejected complaints.

2. **Crash & Recovery Simulation:**
   ```bash
   python -m scripts.demo --crash
   ```
   Simulates a worker dying immediately after writing a complaint to the database. A second worker takes over and successfully finishes the run without duplicating the complaint.

3. **Run Unit Tests:**
   ```bash
   pytest
   ```
   Executes the test suite covering agent delegation, idempotency, tool logic, and end-to-end execution.

4. **Real Gemini Interaction:**
   ```bash
   export GEMINI_API_KEY="..."
   python -m scripts.worker  # Run the background worker in one terminal
   
   # In another terminal, queue a request:
   python -m scripts.ask --student 22CS045 "My fan is broken."
   ```
