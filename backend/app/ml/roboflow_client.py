"""Thin client for the Roboflow Hosted Inference API.

Sends a single JPEG-encoded frame and returns normalised detections.
No local model, no local inference runtime.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import math
import threading
import time
from dataclasses import dataclass, field

import httpx

from ..config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

MOCK_CLASSES = ("pothole", "crack", "alligator-cracking")


class RoboflowConfigError(RuntimeError):
    """Raised when the hosted API is not usable and mocking is disabled."""


@dataclass(slots=True)
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass(slots=True)
class ClientStats:
    calls: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float | None:
        if self.calls == 0:
            return None
        return self.total_latency_ms / self.calls


@dataclass
class RoboflowClient:
    """Calls ``POST https://detect.roboflow.com/{MODEL_ID}`` with base64 JPEG bytes."""

    settings: Settings = field(default_factory=lambda: default_settings)
    stats: ClientStats = field(default_factory=ClientStats)
    _client: httpx.Client | None = field(default=None, init=False, repr=False)
    _stats_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if not self.settings.mock_detector and not self.settings.roboflow_configured:
            raise RoboflowConfigError(
                "ROBOFLOW_API_KEY and MODEL_ID must be set, or MOCK_DETECTOR=1."
            )

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "RoboflowClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def mocked(self) -> bool:
        return self.settings.mock_detector

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            pool_size = max(1, self.settings.max_concurrent_requests)
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.settings.request_timeout_sec),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                limits=httpx.Limits(
                    max_connections=pool_size + 2,
                    max_keepalive_connections=pool_size,
                ),
            )
        return self._client

    def warm_up(self) -> None:
        """Eagerly open the HTTP client so the TCP/TLS handshake happens
        before the frame loop starts, instead of blocking the first detect().
        """
        if not self.settings.mock_detector:
            _ = self.http

    # -- inference ---------------------------------------------------------
    def detect(
        self, jpeg_bytes: bytes, frame_width: int, frame_height: int
    ) -> list[Detection]:
        """Detect on a single frame. Never raises for transient network errors."""
        if self.settings.mock_detector:
            return self._mock_detect(jpeg_bytes, frame_width, frame_height)
        return self._remote_detect(jpeg_bytes, frame_width, frame_height)

    def _remote_detect(
        self, jpeg_bytes: bytes, frame_width: int, frame_height: int
    ) -> list[Detection]:
        url = f"{self.settings.roboflow_base_url.rstrip('/')}/{self.settings.model_id}"
        params = {
            "api_key": self.settings.roboflow_api_key,
            "confidence": int(self.settings.conf_threshold * 100),
            "format": "json",
        }
        payload = base64.b64encode(jpeg_bytes)

        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self.http.post(url, params=params, content=payload)
                elapsed_ms = (time.perf_counter() - started) * 1000.0

                if response.status_code == 429 or response.status_code >= 500:
                    last_error = RuntimeError(
                        f"Roboflow API returned {response.status_code}"
                    )
                    self._backoff(attempt)
                    continue
                if response.status_code in (401, 403):
                    with self._stats_lock:
                        self.stats.failures += 1
                    raise RoboflowConfigError(
                        "Roboflow rejected the API key (HTTP "
                        f"{response.status_code}). Check ROBOFLOW_API_KEY."
                    )
                response.raise_for_status()

                with self._stats_lock:
                    self.stats.calls += 1
                    self.stats.total_latency_ms += elapsed_ms
                return self._parse(response.json(), frame_width, frame_height)
            except RoboflowConfigError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                self._backoff(attempt)

        with self._stats_lock:
            self.stats.failures += 1
        logger.warning("Roboflow inference failed for a frame: %s", last_error)
        return []

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(0.5 * (2**attempt), 4.0))

    def _parse(
        self, body: dict, frame_width: int, frame_height: int
    ) -> list[Detection]:
        """Roboflow returns center-x/center-y/width/height in *inference* pixels."""
        image = body.get("image") or {}
        src_w = float(image.get("width") or frame_width) or frame_width
        src_h = float(image.get("height") or frame_height) or frame_height
        sx = frame_width / src_w
        sy = frame_height / src_h

        out: list[Detection] = []
        for pred in body.get("predictions", []):
            try:
                conf = float(pred.get("confidence", 0.0))
                if conf < self.settings.conf_threshold:
                    continue
                cx = float(pred["x"]) * sx
                cy = float(pred["y"]) * sy
                w = float(pred["width"]) * sx
                h = float(pred["height"]) * sy
            except (KeyError, TypeError, ValueError):
                continue

            x1 = max(0, int(round(cx - w / 2)))
            y1 = max(0, int(round(cy - h / 2)))
            x2 = min(frame_width - 1, int(round(cx + w / 2)))
            y2 = min(frame_height - 1, int(round(cy + h / 2)))
            if x2 <= x1 or y2 <= y1:
                continue

            out.append(
                Detection(
                    class_name=str(pred.get("class", "damage")).lower(),
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                )
            )
        return out

    # -- mock --------------------------------------------------------------
    def _mock_detect(
        self, jpeg_bytes: bytes, frame_width: int, frame_height: int
    ) -> list[Detection]:
        """Deterministic pseudo-detections derived from the frame bytes."""
        with self._stats_lock:
            self.stats.calls += 1
            self.stats.total_latency_ms += 4.0

        digest = hashlib.sha256(jpeg_bytes).digest()
        seed = int.from_bytes(digest[:8], "big")
        count = seed % 4  # 0..3 boxes
        out: list[Detection] = []
        for i in range(count):
            r = (seed >> (i * 7 + 3)) & 0xFFFF
            conf = 0.40 + ((r % 55) / 100.0)
            if conf < self.settings.conf_threshold:
                continue
            bw = int(frame_width * (0.08 + ((r >> 3) % 12) / 100.0))
            bh = int(frame_height * (0.08 + ((r >> 6) % 12) / 100.0))
            cx = int(frame_width * (0.15 + ((r >> 9) % 70) / 100.0))
            cy = int(frame_height * (0.45 + ((r >> 11) % 45) / 100.0))
            x1 = max(0, cx - bw // 2)
            y1 = max(0, cy - bh // 2)
            x2 = min(frame_width - 1, x1 + bw)
            y2 = min(frame_height - 1, y1 + bh)
            if x2 <= x1 or y2 <= y1:
                continue
            out.append(
                Detection(
                    class_name=MOCK_CLASSES[(r >> 2) % len(MOCK_CLASSES)],
                    confidence=round(min(conf, 0.99), 3),
                    bbox=(x1, y1, x2, y2),
                )
            )
        return out


def severity_of(confidence: float) -> str:
    """Bucket a confidence score into a demo 'severity' label."""
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def clamp01(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return min(max(value, 0.0), 1.0)
