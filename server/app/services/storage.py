"""Generated-asset storage: local disk (dev) or a public GCS bucket (prod).

Selected by ``config.ASSET_BACKEND`` ('local' | 'gcs'). Assets are addressed by
a relative KEY like ``{session_id}/cover.png`` or
``{session_id}/characters/{cid}/happy.png`` — never an absolute path — so the
same key round-trips through either backend.

In prod the bucket objects are public-read (uniform bucket-level access +
``allUsers:objectViewer``) and the browser loads them straight from the CDN
(``public_url``); the backend only writes them. Cloud Run's filesystem is
ephemeral and per-instance, so 'local' is dev-only.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import config

# Covers/manifests can change in place (regeneration, runtime TTS); everything
# else is content-addressed and immutable.
_MUTABLE_SUFFIXES = ("cover.png", "manifest.json")


def _cache_control(key: str) -> str:
    if key.endswith(_MUTABLE_SUFFIXES):
        return "public, max-age=3600"
    return "public, max-age=31536000, immutable"


class _LocalBackend:
    """Reads/writes under ``config.GENERATED_DIR``. Assets are served by the
    /api/v1/assets routes off this disk in dev."""

    def __init__(self, root: Path):
        self._root = root

    def _path(self, key: str) -> Path:
        return self._root / key

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.is_file() else None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def local_path(self, key: str) -> Path | None:
        p = self._path(key)
        return p if p.is_file() else None

    def has_prefix(self, prefix: str) -> bool:
        return self._path(prefix).exists()

    def delete_prefix(self, prefix: str) -> None:
        shutil.rmtree(self._path(prefix), ignore_errors=True)

    def public_url(self, key: str) -> str:
        return f"/api/v1/assets/{key}"


class _GCSBackend:
    """Reads/writes a public GCS bucket. The browser fetches objects directly
    from ``public_url`` (CDN); the backend never serves the bytes on the hot
    path."""

    def __init__(self, bucket_name: str, public_base: str):
        from google.cloud import storage as gcs  # lazy: dev never imports this

        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._public_base = public_base.rstrip("/")

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        blob = self._bucket.blob(key)
        blob.cache_control = _cache_control(key)
        blob.upload_from_string(data, content_type=content_type)

    def read(self, key: str) -> bytes | None:
        blob = self._bucket.blob(key)
        return blob.download_as_bytes() if blob.exists() else None

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()

    def local_path(self, key: str) -> Path | None:
        return None

    def has_prefix(self, prefix: str) -> bool:
        prefix = prefix.rstrip("/") + "/"
        return next(iter(self._client.list_blobs(self._bucket, prefix=prefix, max_results=1)), None) is not None

    def delete_prefix(self, prefix: str) -> None:
        prefix = prefix.rstrip("/") + "/"
        for blob in self._client.list_blobs(self._bucket, prefix=prefix):
            blob.delete()

    def public_url(self, key: str) -> str:
        return f"{self._public_base}/{key}"


def _make_backend():
    if config.ASSET_BACKEND == "gcs":
        if not config.GCS_BUCKET:
            raise RuntimeError("ASSET_BACKEND=gcs but GCS_BUCKET is unset")
        base = config.GCS_PUBLIC_BASE or f"https://storage.googleapis.com/{config.GCS_BUCKET}"
        return _GCSBackend(config.GCS_BUCKET, base)
    return _LocalBackend(config.GENERATED_DIR)


backend = _make_backend()
