import argparse
import time

from app.config import GEMINI_MODEL, open_stores, make_providers
from scripts._term import CYAN, DIM, GREEN, RED, RESET


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("text")
    p.add_argument("--student", default="22CS045")
    p.add_argument("--thread")
    a = p.parse_args()
    store, _ = open_stores()
    make_providers(mock=False)
    thread = a.thread or store.create_thread(a.student)
    run_id = store.enqueue(thread, a.text, GEMINI_MODEL)
    print(f"{DIM}thread {thread}{RESET}\n{CYAN}run {run_id}{RESET} queued; waiting for a worker...")
    while (run := store.get_run(run_id))["status"] not in ("succeeded", "failed", "cancelled", "dead"):
        time.sleep(0.5)

    colour = GREEN if run["status"] == "succeeded" else RED
    reply = store.load_history(thread)[-1]["text"] if run["status"] == "succeeded" else run["error_code"]
    print(f"\n{colour}assistant>{RESET} {reply}")


if __name__ == "__main__":
    main()
