"""One opt-in bounded thread; no SMTP calls on public acceptance paths."""
import logging
import threading


class EmailVerificationWorker:
    def __init__(self, dispatcher, *, reset_dispatcher=None, invitation_dispatch=None):
        self.dispatcher = dispatcher
        self.reset_dispatcher = reset_dispatcher
        self.invitation_dispatch = invitation_dispatch
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="email-verification", daemon=False)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.dispatcher.dispatch(limit=1)
                if self.reset_dispatcher is not None:
                    self.reset_dispatcher.dispatch(limit=1)
                if self.invitation_dispatch is not None:
                    self.invitation_dispatch()
            except Exception:
                logging.getLogger(__name__).warning("Email verification dispatch temporarily unavailable")
            self._stop.wait(1)
