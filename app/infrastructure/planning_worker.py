"""Default-off single local planning thread; cooperative stop, no hard cancellation."""
import logging
import threading


class PlanningWorker:
    def __init__(self,service):
        self.service=service
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self._loop,name='shelfcash-planning',daemon=False)

    @property
    def available(self):return self.thread.is_alive() and not self.stop_event.is_set()

    def start(self):self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.service.recover()
                done=self.service.run_one()
            except Exception as error:
                logging.getLogger(__name__).error('Planning execution unavailable (%s)',type(error).__name__)
                done=None
            if done is None:self.stop_event.wait(1)
