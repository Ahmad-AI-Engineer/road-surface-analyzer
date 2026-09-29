"""REST API — upload, poll, detections, history, stats."""

from __future__ import annotations

import csv
import io
import logging
import shutil
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Detection, Job, JobStatus
from ..processing import cancel_job, submit_job
from ..schemas import (
    ClassCount,
    ConfidenceBin,
    DetectionOut,
    DetectionPage,
    JobCreated,
    JobList,
    JobOut,
    JobSummary,
    StatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
CHUNK_SIZE = 1024 * 1024


def _sniff_container(head: bytes) -> str | None:
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska"  # mkv / webm
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    return None


def _job_to_out(job: Job, db: Session) -> JobOut:
    rows = db.execute(
        select(
            Detection.class_name,
            func.count(Detection.id),
            func.avg(Detection.confidence),
            func.max(Detection.confidence),
        )
        .where(Detection.job_id == job.id)
        .group_by(Detection.class_name)
        .order_by(func.count(Detection.id).desc())
    ).all()

    by_class = [
        ClassCount(
            class_name=name, count=int(count), avg_confidence=round(float(avg or 0), 4)
        )
        for name, count, avg, _ in rows
    ]
    summary = JobSummary(
        total_detections=sum(c.count for c in by_class),
        by_class=by_class,
        max_confidence=round(max((float(r[3] or 0) for r in rows), default=0.0), 4),
    )

    out = JobOut.model_validate(job)
    out.summary = summary
    base = settings.media_public_url.rstrip("/")
    out.video_url = f"{base}{job.processed_path}" if job.processed_path else None
    out.thumb_url = f"{base}{job.thumb_path}" if job.thumb_path else None
    return out


@router.post("/jobs", response_model=JobCreated, status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreated:
    original_name = Path(file.filename or "upload.mp4").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )

    head = await file.read(12)
    if _sniff_container(head) is None:
        raise HTTPException(
            status_code=415, detail="File does not look like a supported video container."
        )

    job_id = str(uuid.uuid4())
    settings.ensure_dirs()

    # Guard against filling up the media volume mid-demo: refuse new uploads
    # if there isn't comfortably enough free disk space for them (upload +
    # processed copy + thumbnail all land on the same volume).
    free_bytes = shutil.disk_usage(settings.media_root).free
    required_bytes = settings.max_upload_mb * 1024 * 1024 * 3
    if free_bytes < required_bytes:
        raise HTTPException(
            status_code=507,
            detail="Server is low on storage space. Please try again later or "
            "ask an admin to clear old jobs.",
        )

    dest = settings.uploads_dir / f"{job_id}{suffix}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0

    try:
        with dest.open("wb") as fh:
            fh.write(head)
            written += len(head)
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.max_upload_mb} MB limit.",
                    )
                fh.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        logger.exception("Failed writing upload")
        raise HTTPException(status_code=500, detail="Could not store the upload.") from exc
    finally:
        await file.close()

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    job = Job(
        id=job_id,
        filename=original_name,
        status=JobStatus.queued,
        frame_stride=settings.frame_stride,
        conf_threshold=settings.conf_threshold,
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(submit_job, job_id)
    return JobCreated(job_id=job_id, status=JobStatus.queued, filename=original_name)


@router.get("/jobs", response_model=JobList)
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: JobStatus | None = None,
    db: Session = Depends(get_db),
) -> JobList:
    stmt = select(Job)
    count_stmt = select(func.count(Job.id))
    if status is not None:
        stmt = stmt.where(Job.status == status)
        count_stmt = count_stmt.where(Job.status == status)

    total = db.execute(count_stmt).scalar_one()
    jobs = (
        db.execute(stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return JobList(total=int(total), items=[_job_to_out(j, db) for j in jobs])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job, db)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.queued, JobStatus.processing):
        raise HTTPException(
            status_code=409, detail=f"Job is already {job.status.value}, cannot cancel."
        )

    cancel_job(job_id)

    db.refresh(job)
    return _job_to_out(job, db)


@router.delete("/jobs/{job_id}", status_code=204, response_model=None)
def delete_job(job_id: str, db: Session = Depends(get_db)) -> None:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.processing:
        raise HTTPException(status_code=409, detail="Job is still processing")

    for path in (
        settings.processed_dir / f"{job_id}.mp4",
        settings.thumbs_dir / f"{job_id}.jpg",
    ):
        path.unlink(missing_ok=True)
    for upload in settings.uploads_dir.glob(f"{job_id}.*"):
        upload.unlink(missing_ok=True)

    db.delete(job)
    db.commit()


@router.get("/jobs/{job_id}/detections")
def get_detections(
    job_id: str,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    ordering = (
        (Detection.frame_idx.desc(), Detection.id.desc())
        if order == "desc"
        else (Detection.frame_idx.asc(), Detection.id.asc())
    )
    base = select(Detection).where(Detection.job_id == job_id).order_by(*ordering)

    if format == "csv":
        rows = db.execute(base).scalars().all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["frame_idx", "timestamp_sec", "class_name", "confidence", "x1", "y1", "x2", "y2"]
        )
        for d in rows:
            writer.writerow(
                [d.frame_idx, d.timestamp_sec, d.class_name, d.confidence, *d.bbox]
            )
        buffer.seek(0)
        safe_id = job_id.replace('"', "")
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="detections_{safe_id}.csv"'
            },
        )

    total = db.execute(
        select(func.count(Detection.id)).where(Detection.job_id == job_id)
    ).scalar_one()
    items = db.execute(base.limit(limit).offset(offset)).scalars().all()
    return DetectionPage(
        job_id=job_id,
        total=int(total),
        limit=limit,
        offset=offset,
        items=[DetectionOut.model_validate(d) for d in items],
    )


@router.get("/jobs/{job_id}/timeline")
def get_timeline(
    job_id: str,
    bucket_sec: float = Query(10.0, gt=0, le=120),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = db.execute(
        select(Detection.timestamp_sec, Detection.confidence, Detection.class_name).where(
            Detection.job_id == job_id
        )
    ).all()

    buckets: dict[int, int] = defaultdict(int)
    for ts, _conf, _cls in rows:
        buckets[int(ts // bucket_sec)] += 1

    return {
        "job_id": job_id,
        "bucket_sec": bucket_sec,
        "buckets": [
            {"start_sec": idx * bucket_sec, "count": count}
            for idx, count in sorted(buckets.items())
        ],
    }


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    jobs_total = int(db.execute(select(func.count(Job.id))).scalar_one())
    jobs_done = int(
        db.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.done)
        ).scalar_one()
    )
    jobs_failed = int(
        db.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.failed)
        ).scalar_one()
    )

    class_rows = db.execute(
        select(
            Detection.class_name, func.count(Detection.id), func.avg(Detection.confidence)
        )
        .group_by(Detection.class_name)
        .order_by(func.count(Detection.id).desc())
    ).all()
    by_class = [
        ClassCount(
            class_name=name, count=int(count), avg_confidence=round(float(avg or 0), 4)
        )
        for name, count, avg in class_rows
    ]

    confidences = db.execute(select(Detection.confidence)).scalars().all()
    bins = [0] * 10
    for conf in confidences:
        idx = min(9, max(0, int(float(conf) * 10)))
        bins[idx] += 1
    histogram = [
        ConfidenceBin(bin_start=i / 10, bin_end=(i + 1) / 10, count=count)
        for i, count in enumerate(bins)
    ]

    api_calls = int(db.execute(select(func.sum(Job.api_calls))).scalar() or 0)
    weighted = db.execute(
        select(func.sum(Job.api_latency_ms * Job.api_calls), func.sum(Job.api_calls)).where(
            Job.api_latency_ms.is_not(None)
        )
    ).one()
    avg_latency = (
        round(float(weighted[0]) / float(weighted[1]), 2)
        if weighted[0] and weighted[1]
        else None
    )

    return StatsResponse(
        jobs_total=jobs_total,
        jobs_done=jobs_done,
        jobs_failed=jobs_failed,
        detections_total=sum(c.count for c in by_class),
        by_class=by_class,
        confidence_histogram=histogram,
        api_calls_total=api_calls,
        api_avg_latency_ms=avg_latency,
    )
