"""Application configuration, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # Roboflow Hosted Inference API
    roboflow_api_key: str = Field(default="", alias="ROBOFLOW_API_KEY")
    model_id: str = Field(default="road-damage-medium-9semt/1", alias="MODEL_ID")
    roboflow_base_url: str = Field(
        default="https://detect.roboflow.com", alias="ROBOFLOW_BASE_URL"
    )
    request_timeout_sec: float = Field(default=20.0, alias="REQUEST_TIMEOUT_SEC")
    max_retries: int = Field(default=2, alias="MAX_RETRIES")

    # Pipeline
    conf_threshold: float = Field(default=0.35, alias="CONF_THRESHOLD")
    frame_stride: int = Field(default=5, alias="FRAME_STRIDE")
    max_upload_mb: int = Field(default=200, alias="MAX_UPLOAD_MB")
    mock_detector: bool = Field(default=False, alias="MOCK_DETECTOR")
    inference_width: int = Field(default=640, alias="INFERENCE_WIDTH")
    max_concurrent_requests: int = Field(default=8, alias="MAX_CONCURRENT_REQUESTS")

    # Storage
    media_root: Path = Field(default=Path("/media"), alias="MEDIA_ROOT")
    db_path: Path = Field(default=Path("/data/app.db"), alias="DB_PATH")

    # HTTP
    cors_origins: str = Field(
        default="http://localhost:3007,http://localhost:3006", alias="CORS_ORIGINS"
    )
    media_public_url: str = Field(
        default="http://localhost:3006", alias="MEDIA_PUBLIC_URL"
    )

    @field_validator("conf_threshold")
    @classmethod
    def _clamp_conf(cls, v: float) -> float:
        return min(max(v, 0.0), 1.0)

    @field_validator("frame_stride")
    @classmethod
    def _min_stride(cls, v: int) -> int:
        return max(1, v)

    @field_validator("max_concurrent_requests")
    @classmethod
    def _min_concurrency(cls, v: int) -> int:
        return max(1, v)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.media_root / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.media_root / "processed"

    @property
    def thumbs_dir(self) -> Path:
        return self.media_root / "thumbs"

    @property
    def roboflow_configured(self) -> bool:
        return bool(self.roboflow_api_key and self.model_id)

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.processed_dir, self.thumbs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
