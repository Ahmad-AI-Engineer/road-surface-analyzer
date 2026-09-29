"""Pre-populate the demo with a few finished jobs.

Run inside the backend container (working directory /app):
    docker compose exec backend python /scripts/seed_demo.py

Uses MOCK_DETECTOR semantics by default so seeding never consumes Roboflow quota;
pass --live to use the real hosted API instead.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/app")

from app.config import settings  # noqa: E402
from app.db import init_db, session_scope  # noqa: E402
from app.ml.roboflow_client import RoboflowClient  # noqa: E402
from app.ml.video_pipeline import process_video  # noqa: E402
from app.models import Detection, Job, JobStatus  # noqa: E402

DEMOS = [
    ("highway_segment_A12.mp4", 12),
    ("city_ring_road_night.mp4", 10),
    ("rural_route_44.mp4", 14),
]


def _ensure_sample(path: Path, seconds: int) -> Path:
    if path.exists():
        return path
    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("make_sample.py")),
            str(path),
            "--seconds",
            str(seconds),
            "--width",
            "960",
            "--height",
            "540",
        ],
        check=True,
    )
    return path


def seed(live: bool, stride: int) -> int:
    settings.ensure_dirs()
    init_db()

    cfg = settings.model_copy(
        update={"mock_detector": not live, "frame_stride": stride}
    )
    sample_dir = Path("/samples")
    sample_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for offset, (name, seconds) in enumerate(DEMOS):
        with session_scope() as db:
            existing = db.query(Job).filter(Job.filename == name).first()
            if existing is not None:
                print(f"skip  {name} (already seeded)")
                continue

        source = _ensure_sample(sample_dir / f"seed_{offset}.mp4", seconds)
        job_id = str(uuid.uuid4())
        upload = settings.uploads_dir / f"{job_id}.mp4"
        shutil.copyfile(source, upload)

        out_path = settings.processed_dir / f"{job_id}.mp4"
        thumb_path = settings.thumbs_dir / f"{job_id}.jpg"

        print(f"build {name} ...")
        client = RoboflowClient(settings=cfg)
        try:
            result = process_video(
                upload,
                out_path,
                client=client,
                config=cfg,
                thumb_path=thumb_path,
                progress_cb=lambda pct, _eta, _n: print(
                    f"\r  {pct:5.1f}%", end="", flush=True
                ),
            )
        finally:
            client.close()
        print()

        created_at = datetime.now(timezone.utc) - timedelta(hours=6 * (offset + 1))
        with session_scope() as db:
            job = Job(
                id=job_id,
                filename=name,
                status=JobStatus.done,
                progress=100.0,
                eta_sec=0.0,
                fps_in=round(result.meta.fps, 3),
                duration_sec=round(result.meta.duration_sec, 3),
                width=result.meta.width,
                height=result.meta.height,
                frames_total=result.meta.frames_total,
                frames_processed=result.frames_processed,
                frame_stride=cfg.frame_stride,
                conf_threshold=cfg.conf_threshold,
                api_calls=result.api_calls,
                api_failures=result.api_failures,
                api_latency_ms=(
                    round(result.api_avg_latency_ms, 2)
                    if result.api_avg_latency_ms is not None
                    else None
                ),
                mocked=bool(result.mocked),
                processed_path=f"/processed/{out_path.name}",
                thumb_path=(
                    f"/thumbs/{thumb_path.name}" if result.thumb_path else None
                ),
                created_at=created_at,
                started_at=created_at,
                finished_at=created_at + timedelta(seconds=result.elapsed_sec),
            )
            db.add(job)
            db.flush()
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
                    for d in result.detections
                ]
            )
        created += 1
        print(f"done  {name}: {len(result.detections)} detections")

    print(f"\nSeeded {created} job(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="use the real Roboflow API instead of the mock detector",
    )
    parser.add_argument("--stride", type=int, default=10)
    args = parser.parse_args()
    return seed(args.live, args.stride)


if __name__ == "__main__":
    raise SystemExit(main())
