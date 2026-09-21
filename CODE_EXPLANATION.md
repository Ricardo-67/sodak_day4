# Hostel Complaints Desk: Code Breakdown & Explanation

This document explains what each file in the project does, providing a clear understanding of the codebase's architecture and logic.

## 1. Schema Layer
The database schemas define the rigid rules and structure of our application before any Python code runs.

- **`schema/hostel.sql`**: Contains the schema for the business domain (rooms, students, complaints, notifications, idempotency, and policies). It enforces our primary business rule using a unique index (`CREATE UNIQUE INDEX one_open_issue ON complaint (room_id, issue) WHERE status = 'open';`), which guarantees at the database level that agents cannot accidentally create duplicate open complaints.
- **`schema/agent.sql`**: Contains the internal state for the agentic system. It defines the tables for conversations (`thread`), queued tasks (`run`), message history (`turn`), and tool calls (`tool_call`). This is where the queue and worker leases are maintained.

## 2. Core Application Logic (`app/` directory)

- **`app/db.py`**: A low-level SQLite utility file. It provides helper functions for establishing database connections (`connect`) and wrapping queries in safe, atomic transactions (`transaction`), which automatically commit on success and rollback on errors.
- **`app/hostel_db.py`**: The Data Access Object (DAO) for the hostel domain. It wraps raw SQL queries into Python methods. It implements safe read methods (like `get_room_by_number`) and idempotent write methods (like `raise_complaint`, which relies on `sqlite3.IntegrityError` to safely catch and ignore duplicate complaints). It also handles the initial database seeding in its `migrate` method.
- **`app/memory.py`**: The `RunStore` class manages the agent's memory and job queue, interacting directly with `agent.db`. It handles enqueuing user requests (`enqueue`), claiming tasks for workers with a time-bound lease (`claim`), appending messages to a thread's history (`append`), and loading past conversation context.
- **`app/idempotency.py`**: Provides utilities to generate unique hashes (`idempotency_key`) for every agent action. Keys are deterministically generated based on the agent's place in the conversation, ensuring that if a worker crashes and retries a task, the exact same key will be generated for the exact same tool call.

## 3. Agents & Tools Layer

- **`app/agents.py`**: Defines the multi-agent system structure. It contains the system prompts for the Supervisor, Information (read-only), and Desk (read/write) agents. It provides the `run_specialist` loop, which executes a specialist agent until it finishes its task. It also houses `SupervisorTools`, which exposes the specialists as simple tools to the Supervisor agent.
- **`app/tools/dispatch.py`**: A generic dispatcher utility that validates tool arguments and securely invokes python functions based on the names the LLM requests.
- **`app/tools/hostel_tools.py`**: Connects LLM actions to database operations. It defines two classes (`InformationTools` and `DeskTools`), each with their own strictly limited capabilities. The docstrings on these methods act directly as the tool definitions (prompts) sent to the LLM, describing exactly when and how the agent should use them.

## 4. Execution & Orchestration

- **`app/runner.py`**: Contains `execute_run`, which orchestrates the Supervisor's main loop. It pulls the conversation history from the `RunStore`, formats it for the LLM, invokes the LLM, calls any requested tools (or delegates to specialists), and pushes the final state back to the database. It handles lease timeouts gracefully.
- **`app/worker.py`**: The background daemon loop. It repeatedly polls the queue via `RunStore.claim` to pick up pending or crashed jobs. Once it claims a run, it passes it to `app.runner.execute_run`.

## 5. Providers & Configuration

- **`app/providers.py`**: An abstraction layer over LLM APIs. It contains `GeminiProvider` for making real network calls to the Gemini API, and Mock providers (`ScriptedProvider`, `RoutedMock`) for local, keyless testing and demos.
- **`app/config.py`**: Loads environment variables (like `AGENT_DB`, `HOSTEL_DB`, `GEMINI_MODEL`) and initializes the global dependencies. It switches between real Gemini calls or Mock providers depending on the environment context.

## 6. Scripts & User Interface (`scripts/` directory)

- **`scripts/ask.py`**: A CLI entry point simulating a user interface. It takes a student's roll number and their text request, creates a new thread (or appends to an existing one), and enqueues the run in the database to be picked up by a worker.
- **`scripts/worker.py`**: A CLI script to start a background worker that endlessly polls the queue and processes runs using real Gemini API keys.
- **`scripts/demo.py`**: A comprehensive, self-contained demonstration script. It sets up temporary, in-memory databases, queues simulated questions, and manually runs the worker loop using mock, scripted LLMs. It also includes a `--crash` mode that intentionally intercepts a database write to demonstrate durable recovery mechanisms.
- **`scripts/_term.py`**: Formatting utilities to print colorful logs and agent traces to the terminal during demos.

## 7. Testing (`tests/` directory)
- Contains standard `pytest` testing files ensuring that agents correctly delegate work, tools strictly abide by the rules, and end-to-end simulated crash tests flawlessly recover and continue execution.
