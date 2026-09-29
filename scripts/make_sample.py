"""Generate a short synthetic road video for demos and smoke tests.

Usage (inside the backend container):
    python scripts/make_sample.py samples/road_demo.mp4 --seconds 20
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np


def _road_frame(idx: int, width: int, height: int, fps: int) -> np.ndarray:
    t = idx / fps
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # Sky / horizon gradient
    horizon = int(height * 0.38)
    for y in range(horizon):
        shade = int(40 + (y / max(1, horizon)) * 70)
        frame[y, :] = (shade + 25, shade + 12, shade)

    # Asphalt with perspective
    for y in range(horizon, height):
        depth = (y - horizon) / max(1, height - horizon)
        shade = int(38 + depth * 46)
        frame[y, :] = (shade, shade, shade + 3)

    # Lane edges
    cx = width // 2 + int(math.sin(t * 0.6) * width * 0.03)
    for y in range(horizon, height):
        depth = (y - horizon) / max(1, height - horizon)
        half = int(width * (0.03 + depth * 0.42))
        for x in (cx - half, cx + half):
            if 2 <= x < width - 2:
                cv2.line(frame, (x, y), (x, y), (210, 210, 210), 2)

    # Dashed centre line
    for k in range(-2, 14):
        phase = (k + (t * 2.2) % 1.0) / 14.0
        if phase <= 0:
            continue
        y = horizon + int((height - horizon) * (phase**2.1))
        if y <= horizon or y >= height:
            continue
        depth = (y - horizon) / max(1, height - horizon)
        length = max(2, int(24 * depth))
        thickness = max(1, int(7 * depth))
        cv2.line(frame, (cx, y), (cx, min(height - 1, y + length)), (235, 235, 235), thickness)

    # Pseudo damage blobs that drift toward the camera
    rng = np.random.default_rng(7)
    for i, (offset, seed) in enumerate(zip(rng.uniform(-0.3, 0.3, 6), rng.integers(0, 999, 6))):
        phase = ((t * 0.32) + i / 6.0) % 1.0
        y = horizon + int((height - horizon) * (phase**2.0))
        if y <= horizon + 8 or y >= height - 4:
            continue
        depth = (y - horizon) / max(1, height - horizon)
        x = int(cx + offset * width * depth * 1.6)
        rx = max(3, int(46 * depth))
        ry = max(2, int(20 * depth))
        tone = 18 if seed % 3 == 0 else 26
        cv2.ellipse(frame, (x, y), (rx, ry), int(seed % 180), 0, 360, (tone, tone, tone + 2), -1)
        cv2.ellipse(frame, (x, y), (rx, ry), int(seed % 180), 0, 360, (12, 12, 14), 2)

    cv2.putText(
        frame,
        f"SYNTHETIC ROAD SAMPLE  t={t:5.2f}s",
        (14, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="samples/road_demo.mp4")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to write a browser-playable sample video")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{args.width}x{args.height}", "-r", str(args.fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    total = args.seconds * args.fps
    try:
        for idx in range(total):
            frame = _road_frame(idx, args.width, args.height, args.fps)
            assert proc.stdin is not None
            proc.stdin.write(frame.tobytes())
            if idx % args.fps == 0:
                print(f"\r{idx / total * 100:5.1f}%", end="", flush=True)
    finally:
        if proc.stdin:
            proc.stdin.close()
        code = proc.wait()

    print()
    if code != 0:
        raise SystemExit(f"ffmpeg failed with code {code}")
    print(f"Wrote {out_path} ({args.seconds}s @ {args.fps}fps, {args.width}x{args.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
