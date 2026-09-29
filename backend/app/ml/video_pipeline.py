"""OpenCV frame loop + ffmpeg video rebuild.

Frames are decoded with OpenCV, every ``FRAME_STRIDE``-th frame is sent to the
Roboflow Hosted Inference API, boxes are drawn on *every* frame (detections are
held across skipped frames), and the result is piped to ffmpeg as raw BGR24 and
encoded to browser-playable H.264 / yuv420p / +faststart MP4.

OpenCV's default ``mp4v`` writer produces files Chrome will not play, which is
why ffmpeg is used for the rebuild.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings, settings as default_settings
from .roboflow_client import Detection, RoboflowClient

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, float | None, int], None]
DetectionCallback = Callable[[list["FrameDetection"]], None]

CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "pothole": (60, 76, 231),  # red (BGR)
    "crack": (15, 196, 241),  # amber
    "alligator-cracking": (176, 92, 155),  # violet
    "alligator crack": (176, 92, 155),
    "alligator_cracking": (176, 92, 155),
}
DEFAULT_COLOR = (113, 204, 46)  # green


class VideoPipelineError(RuntimeError):
    pass


class VideoPipelineCancelled(RuntimeError):
    """Raised internally when a caller-supplied cancel_event is set mid-run."""
    pass


@dataclass(slots=True)
class FrameDetection:
    frame_idx: int
    timestamp_sec: float
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass(slots=True)
class VideoMeta:
    width: int
    height: int
    fps: float
    frames_total: int
    duration_sec: float


@dataclass
class PipelineResult:
    meta: VideoMeta
    detections: list[FrameDetection] = field(default_factory=list)
    frames_processed: int = 0
    api_calls: int = 0
    api_failures: int = 0
    api_avg_latency_ms: float | None = None
    elapsed_sec: float = 0.0
    thumb_path: Path | None = None
    mocked: bool = False

    @property
    def achieved_fps(self) -> float:
        if self.elapsed_sec <= 0:
            return 0.0
        return self.frames_processed / self.elapsed_sec

    def counts_by_class(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.detections:
            counts[d.class_name] = counts.get(d.class_name, 0) + 1
        return counts


def _color_for(class_name: str) -> tuple[int, int, int]:
    return CLASS_COLORS.get(class_name.lower().strip(), DEFAULT_COLOR)


def probe_video(path: Path) -> VideoMeta:
    """Read stream metadata with ffprobe, falling back to OpenCV."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            raw = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            ).stdout
            data = json.loads(raw)
            stream = (data.get("streams") or [{}])[0]
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            fps = _parse_rate(stream.get("avg_frame_rate"))
            duration = float(
                stream.get("duration") or data.get("format", {}).get("duration") or 0.0
            )
            frames = int(stream.get("nb_frames") or 0)
            if not frames and fps and duration:
                frames = int(round(fps * duration))
            if width and height and fps > 0:
                return VideoMeta(width, height, fps, frames, duration)
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.debug("ffprobe failed, falling back to OpenCV: %s", exc)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoPipelineError(f"Cannot open video: {path.name}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()
    if width <= 0 or height <= 0:
        raise VideoPipelineError(f"Unreadable video dimensions: {path.name}")
    duration = frames / fps if fps else 0.0
    return VideoMeta(width, height, fps, frames, duration)


def _parse_rate(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(value)
    except ValueError:
        return 0.0


def _draw(frame: np.ndarray, detections: list[Detection], stale: bool) -> None:
    frame_h, frame_w = frame.shape[:2]
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        color = _color_for(det.class_name)
        thickness = 4 if not stale else 3
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        label = f"{det.class_name} {det.confidence:.2f}"
        (tw, th), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2
        )
        label_h = th + baseline + 10
        label_w = tw + 12
        # Center the label vertically on the box's top border so it visually
        # overlaps the line, then clamp so it always stays on-screen.
        label_top = max(0, min(y1 - label_h // 2, frame_h - label_h))
        label_left = max(0, min(x1, frame_w - label_w))
        cv2.rectangle(
            frame,
            (label_left, label_top),
            (label_left + label_w, label_top + label_h),
            color,
            -1,
        )
        cv2.putText(
            frame,
            label,
            (label_left + 6, label_top + th + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


def _overlay_hud(frame: np.ndarray, text: str) -> None:
    h = frame.shape[0]
    cv2.rectangle(frame, (0, h - 28), (frame.shape[1], h), (28, 24, 20), -1)
    cv2.putText(
        frame,
        text,
        (10, h - 9),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (230, 230, 230),
        1,
        cv2.LINE_AA,
    )


def _encode_for_inference(frame: np.ndarray, target_width: int) -> bytes:
    h, w = frame.shape[:2]
    if target_width and w > target_width:
        scale = target_width / w
        frame = cv2.resize(
            frame, (target_width, int(h * scale)), interpolation=cv2.INTER_AREA
        )
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise VideoPipelineError("Failed to JPEG-encode frame")
    return buf.tobytes()


def _start_ffmpeg(
    out_path: Path, width: int, height: int, fps: float
) -> subprocess.Popen:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoPipelineError("ffmpeg is not installed in this environment")
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.4f}",
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def process_video(
    input_path: Path,
    output_path: Path,
    *,
    client: RoboflowClient | None = None,
    config: Settings | None = None,
    thumb_path: Path | None = None,
    progress_cb: ProgressCallback | None = None,
    detection_cb: DetectionCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> PipelineResult:
    cfg = config or default_settings
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise VideoPipelineError(f"Input video not found: {input_path}")

    meta = probe_video(input_path)
    owns_client = client is None
    client = client or RoboflowClient(settings=cfg)
    # Open the HTTP client (TCP/TLS handshake) now, in the background, so it
    # overlaps with cv2.VideoCapture/ffmpeg startup instead of adding latency
    # to the very first detect() call in the frame loop below.
    warm_up_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rda-warmup")
    warm_up_future = warm_up_pool.submit(client.warm_up)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        warm_up_pool.shutdown(wait=False, cancel_futures=True)
        if owns_client:
            client.close()
        raise VideoPipelineError(f"Cannot open video: {input_path.name}")

    # Even dimensions are required by yuv420p.
    out_w = meta.width - (meta.width % 2)
    out_h = meta.height - (meta.height % 2)

    proc = _start_ffmpeg(output_path, out_w, out_h, meta.fps or 25.0)
    result = PipelineResult(meta=meta, mocked=client.mocked)

    stride = max(1, cfg.frame_stride)
    fps = meta.fps or 25.0
    last_detections: list[Detection] = []
    best_conf = -1.0
    best_frame: np.ndarray | None = None
    frame_idx = 0
    # Initialized to match the "nudge" value emitted below so the first
    # real frame-based update can never report a *lower* percentage than
    # what the UI already shows (that visible regression was the bug).
    last_reported_pct = 0.5
    started = time.perf_counter()

    # Nudge the progress bar off 0% immediately so the UI doesn't look frozen
    # while the first (unavoidable) Roboflow round-trip is in flight.
    if progress_cb:
        progress_cb(last_reported_pct, None, 0)

    warm_up_future.result()
    warm_up_pool.shutdown(wait=True)

    # Roboflow inference is a network round-trip per sampled frame, so it's
    # the pipeline's bottleneck. Dispatch those calls to a small thread pool
    # so several requests are in flight concurrently instead of stalling the
    # whole pipeline on each one. Frames are still written to ffmpeg strictly
    # in original order via the `pending` buffer below.
    max_workers = max(1, cfg.max_concurrent_requests)
    buffer_limit = max_workers * stride

    pending: deque[tuple[int, np.ndarray, float, Future | None]] = deque()

    def _drain_one() -> None:
        nonlocal last_detections, best_conf, best_frame, last_reported_pct
        pidx, pframe, ptimestamp, pfut = pending.popleft()

        if pfut is not None:
            detections = pfut.result()
            last_detections = detections
            new_records: list[FrameDetection] = []
            for det in detections:
                record = FrameDetection(
                    frame_idx=pidx,
                    timestamp_sec=round(ptimestamp, 3),
                    class_name=det.class_name,
                    confidence=round(det.confidence, 4),
                    bbox=det.bbox,
                )
                new_records.append(record)
                result.detections.append(record)
                if det.confidence > best_conf:
                    best_conf = det.confidence
                    best_frame = pframe.copy()
            if detection_cb is not None and new_records:
                detection_cb(new_records)

        _draw(pframe, last_detections, stale=pfut is None)
        _overlay_hud(
            pframe,
            f"t={ptimestamp:6.2f}s  frame {pidx}  "
            f"detections {len(last_detections)}"
            + ("  [MOCK]" if client.mocked else ""),
        )

        if proc.stdin is None:
            raise VideoPipelineError("ffmpeg stdin unavailable")
        try:
            proc.stdin.write(pframe.tobytes())
        except BrokenPipeError as exc:
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise VideoPipelineError(f"ffmpeg terminated early: {stderr}") from exc

        frames_done = pidx + 1
        result.frames_processed = frames_done

        if progress_cb and meta.frames_total > 0:
            # Clamp to last_reported_pct so a slow first batch can never
            # report a percentage lower than what the UI already shows.
            pct = max(last_reported_pct, min(99.0, frames_done / meta.frames_total * 100.0))
            if pct - last_reported_pct >= 1.0:
                elapsed = time.perf_counter() - started
                rate = frames_done / elapsed if elapsed > 0 else 0.0
                remaining = meta.frames_total - frames_done
                eta = remaining / rate if rate > 0 else None
                progress_cb(pct, eta, frames_done)
                last_reported_pct = pct

    cancelled = False
    detect_pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rda-detect")
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            ok, frame = cap.read()
            if not ok:
                break

            if out_w != meta.width or out_h != meta.height:
                frame = frame[:out_h, :out_w]

            timestamp = frame_idx / fps
            is_sampled = frame_idx % stride == 0

            future: Future | None = None
            if is_sampled:
                jpeg = _encode_for_inference(frame, cfg.inference_width)
                future = detect_pool.submit(client.detect, jpeg, out_w, out_h)

            pending.append((frame_idx, frame, timestamp, future))
            frame_idx += 1

            while len(pending) > buffer_limit:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                _drain_one()

            if cancelled:
                break

        if not cancelled:
            while pending:
                _drain_one()
    finally:
        detect_pool.shutdown(wait=not cancelled, cancel_futures=cancelled)
        cap.release()
        if proc.stdin:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        return_code = proc.wait()
        if proc.stderr:
            proc.stderr.close()
        if owns_client:
            client.close()

    if cancelled:
        raise VideoPipelineCancelled("Job cancelled by user")

    if return_code != 0:
        raise VideoPipelineError(
            f"ffmpeg failed ({return_code}): {stderr_bytes.decode(errors='replace')[:500]}"
        )
    if result.frames_processed == 0:
        raise VideoPipelineError("No frames could be decoded from the input video")

    result.elapsed_sec = time.perf_counter() - started
    result.api_calls = client.stats.calls
    result.api_failures = client.stats.failures
    result.api_avg_latency_ms = client.stats.avg_latency_ms
    result.meta.frames_total = result.frames_processed
    result.meta.duration_sec = result.frames_processed / fps

    if thumb_path is not None:
        thumb_source = best_frame
        if thumb_source is None:
            cap2 = cv2.VideoCapture(str(input_path))
            ok, thumb_source = cap2.read()
            cap2.release()
            if not ok:
                thumb_source = None
        if thumb_source is not None:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            th, tw = thumb_source.shape[:2]
            scale = 480 / tw if tw > 480 else 1.0
            thumb = (
                cv2.resize(thumb_source, (int(tw * scale), int(th * scale)))
                if scale != 1.0
                else thumb_source
            )
            cv2.imwrite(
                str(thumb_path), thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
            )
            result.thumb_path = thumb_path

    if progress_cb:
        progress_cb(100.0, 0.0, result.frames_processed)

    return result


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the road damage video pipeline")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--stride", type=int, default=None)
    parser.add_argument("--thumb", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = default_settings
    if args.stride:
        cfg = cfg.model_copy(update={"frame_stride": args.stride})

    result = process_video(
        Path(args.input),
        Path(args.output),
        config=cfg,
        thumb_path=Path(args.thumb) if args.thumb else None,
        progress_cb=lambda pct, eta, n: print(
            f"\r{pct:5.1f}%  frame {n}  eta {eta if eta is None else round(eta, 1)}s",
            end="",
            flush=True,
        ),
    )
    print()
    print(f"frames processed : {result.frames_processed}")
    print(f"achieved fps     : {result.achieved_fps:.2f}")
    print(f"roboflow calls   : {result.api_calls} (failures: {result.api_failures})")
    print(
        "avg api latency  : "
        + (
            "n/a"
            if result.api_avg_latency_ms is None
            else f"{result.api_avg_latency_ms:.1f} ms"
        )
    )
    print(f"mock detector    : {result.mocked}")
    print("detections by class:")
    for name, count in sorted(result.counts_by_class().items()):
        print(f"  {name:24s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
