"""Object storage for dataset files and result artifacts.

Local development writes to a directory; AWS uses S3 through boto3. Callers only
see `put_bytes` / `get_bytes` / `exists`, so the rest of the code does not care
which backend is active.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from quantlab.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...


def _check_key(key: str) -> str:
    if not key or key.startswith("/") or ".." in key.split("/"):
        raise StorageError(f"Invalid storage key: {key!r}")
    return key


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        return self.root / _check_key(key)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic rename so readers never see a partial file
        return key

    def get_bytes(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"Object not found: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage:
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        client=None,
        region: str | None = None,
        endpoint_url: str | None = None,
    ):
        if not bucket:
            raise StorageError("S3_BUCKET must be set when STORAGE_BACKEND=s3")
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}{_check_key(key)}"

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(key),
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"S3 upload failed for {key}: {exc}") from exc
        return key

    def get_bytes(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            return resp["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise StorageError(f"Object not found: {key}") from exc
            raise StorageError(f"S3 download failed for {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"S3 download failed for {key}: {exc}") from exc

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise StorageError(f"S3 head failed for {key}: {exc}") from exc


class DbStorage:
    """Objects as rows in `stored_objects`. Each call uses its own short transaction,
    so a put is durable before the caller records the key elsewhere."""

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from quantlab.db import transaction
        from quantlab.models import StoredObject

        stmt = pg_insert(StoredObject).values(
            key=_check_key(key), content_type=content_type, data=data
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"data": stmt.excluded.data, "content_type": stmt.excluded.content_type},
        )
        with transaction() as s:
            s.execute(stmt)
        return key

    def get_bytes(self, key: str) -> bytes:
        from quantlab.db import transaction
        from quantlab.models import StoredObject

        with transaction() as s:
            obj = s.get(StoredObject, _check_key(key))
            if obj is None:
                raise StorageError(f"Object not found: {key}")
            return obj.data

    def exists(self, key: str) -> bool:
        from quantlab.db import transaction
        from quantlab.models import StoredObject

        with transaction() as s:
            return s.get(StoredObject, _check_key(key)) is not None


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "db":
        return DbStorage()
    if settings.storage_backend == "s3":
        return S3Storage(
            settings.s3_bucket,
            settings.s3_prefix,
            region=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
        )
    return LocalStorage(settings.local_storage_dir)


@lru_cache
def get_storage() -> Storage:
    return build_storage(get_settings())
