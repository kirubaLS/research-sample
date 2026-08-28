"""Object storage for page images, mark crops and assembled PDFs.

Two backends behind one interface: the local filesystem for a laptop, and any
S3-compatible service for production. Blobs never go in the database.

Data residency note: student page images contain handwriting, so the bucket should sit in
India (``ap-south-1``, or Cloudflare R2 with a jurisdictional restriction). Only *mark
crops* — a picture of a single digit, with no name and no substantive handwriting — ever
cross the training boundary.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    uri: str
    sha256: str
    size: int


class ObjectStore(Protocol):
    def put(
        self, key: str, data: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StoredObject: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


def _digest(data: BinaryIO) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: data.read(1 << 20), b""):
        h.update(chunk)
        size += len(chunk)
    data.seek(0)
    return h.hexdigest(), size


class LocalObjectStore:
    """Filesystem-backed. Fine for development; not for a multi-instance deployment."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("key escapes the storage root")
        return path

    def put(
        self, key: str, data: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        sha, size = _digest(data)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            shutil.copyfileobj(data, fh)
        return StoredObject(uri=f"file://{path}", sha256=sha, size=size)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3ObjectStore:
    """Any S3-compatible service: AWS S3, Cloudflare R2, MinIO.

    ``boto3`` is an optional dependency — install the ``storage`` extra to use this.
    """

    def __init__(self, bucket: str, *, endpoint_url: str | None, region: str,
                 access_key: str | None, secret_key: str | None):
        import boto3  # noqa: PLC0415

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(
        self, key: str, data: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        sha, size = _digest(data)
        self.client.upload_fileobj(
            data, self.bucket, key,
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
        return StoredObject(uri=f"s3://{self.bucket}/{key}", sha256=sha, size=size)

    def open(self, key: str) -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


def get_object_store() -> ObjectStore:
    s = get_settings()
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            raise RuntimeError("YAADHUM_S3_BUCKET is required when storage_backend is 's3'")
        return S3ObjectStore(
            s.s3_bucket, endpoint_url=s.s3_endpoint_url, region=s.s3_region,
            access_key=s.s3_access_key_id, secret_key=s.s3_secret_access_key,
        )
    return LocalObjectStore(s.object_store_root)
