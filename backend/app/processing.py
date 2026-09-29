"""Background job execution — a single worker thread, no broker."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from .config import settings
from .db import session_scope
from .ml.roboflow_client import RoboflowClient, RoboflowConfigError
from .ml.video_pipeline import (
    FrameDetection,
    PipelineResult,
    VideoPipelineCancelled,
    VideoPipelineError,
    process_video,
)
from .models import Detection, Job, JobStatus

logger = logging.getLogger(__name__)

# Detections are flushed to SQLite in batches so the UI can show them live.
FLUSH_EVERY = 25

# One job at a time: keeps Roboflow API usage predictable and CPU load sane.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rda-worker")
_lock = threading.Lock()

# Tracks in-flight/queued jobs so they can be cancelled on request. Guarded by
# _registry_lock (separate from _lock, which only wraps process_video calls).
_registry_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}
_futures: dict[str, Future] = {}


def submit_job(job_id: str) -> None:
    cancel_event = threading.Event()
    with _registry_lock:
        _cancel_events[job_id] = cancel_event
    future = _executor.submit(_run_job_safe, job_id, cancel_event)
    with _registry_lock:
        _futures[job_id] = future


def cancel_job(job_id: str) -> bool:
    """Request cancellation of a queued or processing job.

    Returns True if a cancellation was actioned, False if there was nothing
    to cancel (job unknown, or already finished/failed/cancelled).
    """
    with _registry_lock:
        future = _futures.get(job_id)
        cancel_event = _cancel_events.get(job_id)

    if future is not None and future.cancel():
        # Still queued behind the single worker thread, never started.
        _mark_cancelled(job_id)
        _forget(job_id)
        return True

    if cancel_event is not None:
        # Already running: the pipeline's frame loop polls this Event and
        # will unwind (raising VideoPipelineCancelled) within a frame or two.
        cancel_event.set()
        return True

    return False


def _forget(job_id: str) -> None:
    with _registry_lock:
        _cancel_events.pop(job_id, None)
        _futures.pop(job_id, None)


def _mark_cancelled(job_id: str, out_path: Path | None = None, thumb_path: Path | None = None) -> None:
    with session_scope() as db:
        db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=JobStatus.cancelled,
                error=None,
                eta_sec=None,
                finished_at=datetime.now(timezone.utc),
            )
        )
    for path in (out_path, thumb_path):
        if path is not None:
            path.unlink(missing_ok=True)


def shutdown(wait: bool = False) -> None:
    _executor.shutdown(wait=wait, cancel_futures=True)


def reap_interrupted_jobs() -> int:
    """Mark jobs left mid-flight by a previous process as failed."""
    with session_scope() as db:
        result = db.execute(
            update(Job)
            .where(Job.status.in_([JobStatus.processing, JobStatus.queued]))
            .values(
                status=JobStatus.failed,
                error="Interrupted by a backend restart.",
                finished_at=datetime.now(timezone.utc),
            )
        )
        return result.rowcount or 0


def _run_job_safe(job_id: str, cancel_event: threading.Event) -> None:
    try:
        _run_job(job_id, cancel_event)
    except Exception:  # noqa: BLE001 - worker thread must never die silently
        logger.exception("Job %s crashed", job_id)
        _fail(job_id, "Unexpected internal error while processing the video.")
    finally:
        _forget(job_id)


def _run_job(job_id: str, cancel_event: threading.Event) -> None:
    out_path = settings.processed_dir / f"{job_id}.mp4"
    thumb_path = settings.thumbs_dir / f"{job_id}.jpg"

    if cancel_event.is_set():
        # Cancelled while queued, but the worker had already popped it off
        # the executor's internal queue before future.cancel() could apply.
        _mark_cancelled(job_id)
        return

    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            logger.warning("Job %s disappeared before processing", job_id)
            return
        upload_path = settings.uploads_dir / f"{job_id}{Path(job.filename).suffix.lower()}"
        job.status = JobStatus.processing
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0.0
        job.frame_stride = settings.frame_stride
        job.conf_threshold = settings.conf_threshold

    def on_progress(pct: float, eta: float | None, frames_done: int) -> None:
        with session_scope() as db:
            db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(progress=round(pct, 2), eta_sec=eta, frames_processed=frames_done)
            )

    buffer: list[FrameDetection] = []

    def flush(force: bool = False) -> None:
        if not buffer or (not force and len(buffer) < FLUSH_EVERY):
            return
        batch, buffer[:] = list(buffer), []
        with session_scope() as db:
            db.bulk_save_objects(
                [
                    Detection(
                        job_id=job_id,
                        frame_idx=d.frame_idx,
                        timestamp_sec=d.timestamp_sec,
                        class_name=d.class_name,
                        confidence=d.confidence,
                        bbox=list(d.bbox),
                    )
                    for d in batch
                ]
            )

    def on_detections(found: list[FrameDetection]) -> None:
        buffer.extend(found)
        flush()

    client: RoboflowClient | None = None
    try:
        client = RoboflowClient(settings=settings)
        with _lock:
            result = process_video(
                upload_path,
                out_path,
                client=client,
                config=settings,
                thumb_path=thumb_path,
                progress_cb=on_progress,
                detection_cb=on_detections,
                cancel_event=cancel_event,
            )
        flush(force=True)
    except RoboflowConfigError as exc:
        _fail(job_id, str(exc))
        return
    except VideoPipelineCancelled:
        flush(force=True)
        _mark_cancelled(job_id, out_path, thumb_path)
        return
    except VideoPipelineError as exc:
        _fail(job_id, str(exc))
        return
    finally:
        if client is not None:
            client.close()

    _persist_result(job_id, result, out_path, thumb_path)


def _persist_result(
    job_id: str, result: PipelineResult, out_path: Path, thumb_path: Path
) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return

        job.status = JobStatus.done
        job.progress = 100.0
        job.eta_sec = 0.0
        job.width = result.meta.width
        job.height = result.meta.height
        job.fps_in = round(result.meta.fps, 3)
        job.duration_sec = round(result.meta.duration_sec, 3)
        job.frames_total = result.meta.frames_total
        job.frames_processed = result.frames_processed
        job.api_calls = result.api_calls
        job.api_failures = result.api_failures
        job.api_latency_ms = (
            round(result.api_avg_latency_ms, 2)
            if result.api_avg_latency_ms is not None
            else None
        )
        job.mocked = bool(result.mocked)
        job.processed_path = f"/processed/{out_path.name}"
        job.thumb_path = (
            f"/thumbs/{thumb_path.name}" if result.thumb_path is not None else None
        )
        job.error = None
        job.finished_at = datetime.now(timezone.utc)

    logger.info(
        "Job %s done: %d frames, %d detections, %d Roboflow calls",
        job_id,
        result.frames_processed,
        len(result.detections),
        result.api_calls,
    )


def _fail(job_id: str, message: str) -> None:
    logger.error("Job %s failed: %s", job_id, message)
    try:
        with session_scope() as db:
            db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    status=JobStatus.failed,
                    error=message[:1000],
                    eta_sec=None,
                    finished_at=datetime.now(timezone.utc),
                )
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not record failure for job %s", job_id)


def queued_or_processing_count() -> int:
    with session_scope() as db:
        rows = db.execute(
            select(Job.id).where(
                Job.status.in_([JobStatus.queued, JobStatus.processing])
            )
        ).all()
        return len(rows)
