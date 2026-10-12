"""Supported native app entrypoint with an owned local graceful stop file."""
import json
import sys
import threading
import time

import uvicorn

from scripts.integration import PRIVATE, settings, write_json


def main() -> int:
    run_id = sys.argv[1]
    from app.main import create_app
    server = uvicorn.Server(uvicorn.Config(create_app(settings()), host="127.0.0.1", port=18001,
                                          log_level="info", access_log=True))
    finished = threading.Event()

    def watch():
        while not finished.wait(0.2):
            path = PRIVATE / "stop.json"
            if path.exists():
                try:
                    if json.loads(path.read_text(encoding="utf-8")).get("run_id") == run_id:
                        server.should_exit = True
                        return
                except (OSError, ValueError):
                    continue

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    code = 1
    try:
        server.run()
        code = 0 if server.started else 1
        return code
    finally:
        finished.set()
        thread.join(timeout=1)
        write_json(PRIVATE / "server-exit.json", {"run_id": run_id, "exit_code": code, "finished_at_unix": time.time()})


if __name__ == "__main__":
    raise SystemExit(main())
