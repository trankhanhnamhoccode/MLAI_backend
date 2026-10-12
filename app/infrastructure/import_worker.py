"""One bounded local execution thread; no broker, live-config retry or GET work."""

import logging
import threading


class ImportWorker:
    def __init__(self, service):
        self.service = service
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._loop, name="shelfcash-import", daemon=False
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()

    def _loop(self):
        try:
            self.service.recover()
        except Exception as e:
            logging.getLogger(__name__).error(
                "Import recovery failed (%s)", type(e).__name__
            )
        while not self.stop_event.is_set():
            try:
                done = self.service.run_one()
            except Exception as e:
                logging.getLogger(__name__).error(
                    "Import execution failed (%s)", type(e).__name__
                )
                done = None
            if done is None:
                self.stop_event.wait(1)
