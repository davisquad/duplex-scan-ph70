"""One running and one replaceable pending task for a preview lane."""
from threading import Condition, Thread


class LatestWorker:
    def __init__(self, name):
        self.condition = Condition()
        self.pending = None
        self.closed = False
        self.thread = Thread(target=self._run,name=name,daemon=True)
        self.thread.start()

    def submit(self, task):
        with self.condition:
            if not self.closed:
                self.pending = task
                self.condition.notify()

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.pending is not None)
                if self.closed: return
                task,self.pending = self.pending,None
            # UI tasks translate exceptions to queue events themselves.
            task()
