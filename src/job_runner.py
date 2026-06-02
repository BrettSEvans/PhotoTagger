import logging
import queue
import threading
from typing import Callable, Dict, Optional

from src.db import Database

logger = logging.getLogger(__name__)


class LocalJobRunner:
    """Single-process background runner for local PhotoTagger jobs."""

    def __init__(self, db: Database):
        self.db = db
        self._tasks: "queue.Queue[tuple[int, Callable[[], Dict]]]" = queue.Queue()
        self._thread = threading.Thread(target=self._work_loop, daemon=True)
        self._thread.start()

    def submit(self, job_type: str, payload: Optional[Dict], task: Callable[[int], Dict]) -> int:
        job_id = self.db.create_processing_job(job_type, payload or {})
        self._tasks.put((job_id, task))
        return job_id

    def _work_loop(self):
        while True:
            job_id, task = self._tasks.get()
            try:
                self.db.update_processing_job(job_id, status="running", progress=5)
                result = task(job_id)  # Pass job_id to task so it can update progress
                self.db.update_processing_job(job_id, status="succeeded", progress=100, result=result)
            except Exception as exc:
                logger.exception("Processing job %s failed", job_id)
                self.db.update_processing_job(job_id, status="failed", error=str(exc))
            finally:
                self._tasks.task_done()
