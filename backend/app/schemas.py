"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import JobStatus


class HealthResponse(BaseModel):
    status: str = "ok"
    roboflow_configured: bool
    mock_detector: bool
    model_id: str
    frame_stride: int
    conf_threshold: float


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    frame_idx: int
    timestamp_sec: float
    class_name: str
    confidence: float
    bbox: list[int]


class DetectionPage(BaseModel):
    job_id: str
    total: int
    limit: int
    offset: int
    items: list[DetectionOut]


class ClassCount(BaseModel):
    class_name: str
    count: int
    avg_confidence: float


class JobSummary(BaseModel):
    total_detections: int = 0
    by_class: list[ClassCount] = Field(default_factory=list)
    max_confidence: float = 0.0


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: JobStatus
    progress: float
    eta_sec: float | None = None
    fps_in: float | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    frames_total: int
    frames_processed: int
    frame_stride: int
    conf_threshold: float
    api_calls: int
    api_latency_ms: float | None = None
    api_failures: int
    mocked: bool
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    video_url: str | None = None
    thumb_url: str | None = None
    summary: JobSummary = Field(default_factory=JobSummary)


class JobCreated(BaseModel):
    job_id: str
    status: JobStatus
    filename: str


class JobList(BaseModel):
    total: int
    items: list[JobOut]


class TimelineBucket(BaseModel):
    start_sec: float
    count: int


class ConfidenceBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class StatsResponse(BaseModel):
    jobs_total: int
    jobs_done: int
    jobs_failed: int
    detections_total: int
    by_class: list[ClassCount]
    confidence_histogram: list[ConfidenceBin]
    api_calls_total: int
    api_avg_latency_ms: float | None = None
