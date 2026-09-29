"""ORM models: jobs and their detections."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16),
        default=JobStatus.queued,
        nullable=False,
        index=True,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eta_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    fps_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frames_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    frame_stride: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    conf_threshold: Mapped[float] = mapped_column(Float, default=0.35, nullable=False)

    api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    api_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mocked: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)

    processed_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    detections: Mapped[list["Detection"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    frame_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    class_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox: Mapped[list[int]] = mapped_column(JSON, nullable=False)

    job: Mapped[Job] = relationship(back_populates="detections")


Index("ix_detections_job_frame", Detection.job_id, Detection.frame_idx)
