"""Explicitly enabled bounded local worker, no email/provider or startup probe."""
import logging
import threading


class NotificationWorker:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="shelfcash-notifications", daemon=False)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.dispatcher.dispatch(limit=20)
            except Exception as error:
                logging.getLogger(__name__).error("Notification dispatch failed (%s)", type(error).__name__)
            self.stop_event.wait(1)
