import time
import logging


logger = logging.getLogger(__name__)


class Timer:

    def __init__(self):
        self.times = []
        self.start = time.perf_counter()
        self.current = self.start
        self.name = None

    def time(self, name):
        # add time of previous action
        self._add_time(self.name)
        self.name = name

    def _add_time(self, name):
        now = time.perf_counter()
        duration = now - self.current
        self.current = now
        if name is not None:
            self.times.append((name, duration))

    def log_times(self):
        self.time(None)
        tp = []
        for s, t in self.times:
            tp.append(f'{s}:{t * 1000:3.0f}')
        logger.info(f'Duration: {(self.current - self.start) * 1000.0:5.3f} ms')
        logger.debug(f'Times: {tp}')
