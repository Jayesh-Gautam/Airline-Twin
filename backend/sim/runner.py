"""Background clock: every 250 ms of real time, advance the simulation by
speed x elapsed and write the changes to MongoDB."""
import threading
import time
from datetime import timedelta

from . import store
from .engine import Engine

SPEEDS = [60, 300, 900, 1800, 3600]          # sim seconds per real second (1 min/s ... 1 h/s)


class Runner:
    def __init__(self, db, params):
        self.db, self.params = db, params
        self.lock = threading.RLock()
        store.ensure_indexes(db)
        self.engine = store.load(db, params)
        st = db.simulation_state.find_one({"_id": "state"}) or {}
        self.speed = st.get("speed", 900)
        self.running = False                    # always paused after a backend restart
        if self.engine is None:
            self.engine = Engine(params)
            self.engine.advance_to(self.engine.clock)
        self.error = None
        self.version = 0
        self._flush()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="sim-clock")
        self.thread.start()

    def _flush(self):
        try:
            store.flush(self.db, self.engine, self.running, self.speed)
            self.error = None
        except Exception as e:                  # keep simulating; report on /sim/state
            self.error = f"MongoDB write failed: {e}"

    def _loop(self):
        last = time.monotonic()
        while not self._stop.wait(0.25):
            now = time.monotonic()
            dt, last = now - last, now
            with self.lock:
                if self.running:
                    self.engine.advance_to(self.engine.clock + timedelta(seconds=dt * self.speed))
                    self.version += 1
                self._flush()

    # ---- controls
    def start(self):
        with self.lock:
            self.running = True
            self._flush()

    def pause(self):
        with self.lock:
            self.running = False
            self._flush()

    def set_speed(self, speed):
        with self.lock:
            self.speed = int(speed)
            self._flush()

    def next_day(self):
        with self.lock:
            self.engine.advance_to(self.engine.next_day_start())
            self.version += 1
            self._flush()

    def advance(self, days):
        """Fast-forward whole days (to midnight), e.g. to fill a month or a year quickly."""
        with self.lock:
            self.engine.advance_to(self.engine.next_day_start() + timedelta(days=int(days) - 1))
            self.version += 1
            self._flush()

    def scenario(self, changes):
        with self.lock:
            self.engine.set_scenario(changes)
            self.version += 1
            self._flush()

    def reset(self, seed=None, start_date=None):
        with self.lock:
            self.running = False
            store.reset(self.db)
            kw = {}
            if seed is not None:
                kw["seed"] = int(seed)
            if start_date:
                kw["start_date"] = start_date
            self.engine = Engine(self.params, **kw)
            self.engine.advance_to(self.engine.clock)
            self.version += 1
            self._flush()

    def stop(self):
        self._stop.set()
