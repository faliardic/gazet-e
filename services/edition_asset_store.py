"""Isolated immutable development object store for verified Q08 assets."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_ASSET_BYTES = 8 * 1024 * 1024
_ASSET_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")
_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AssetStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredAsset:
    asset_id: str
    media_type: str
    width: int
    height: int
    byte_count: int


class DevelopmentAssetStore:
    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("development asset root must be absolute")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise ValueError("development asset root cannot be a symlink")
        self._root = root.resolve(strict=True)

    @property
    def root(self) -> Path:
        return self._root

    def put(
        self,
        *,
        asset_id: str,
        content_hash: str,
        media_type: str,
        width: int,
        height: int,
        data: bytes,
    ) -> StoredAsset:
        hex_id = _asset_hex(asset_id)
        if content_hash != asset_id:
            raise AssetStoreError("asset identity does not match content hash")
        self._validate_bytes(hex_id, media_type, width, height, data)
        target = self._target(hex_id, create_parent=True)
        if target.exists():
            existing = self._read_bounded(target)
            self._validate_bytes(hex_id, media_type, width, height, existing)
            if existing != data:
                raise AssetStoreError("immutable asset content conflict")
            return StoredAsset(asset_id, media_type, width, height, len(existing))

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".pending-",
                suffix=".webp",
                dir=target.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, target)
            except FileExistsError:
                existing = self._read_bounded(target)
                self._validate_bytes(hex_id, media_type, width, height, existing)
                if existing != data:
                    raise AssetStoreError("immutable asset content conflict")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return StoredAsset(asset_id, media_type, width, height, len(data))

    def read(
        self,
        *,
        asset_hex: str,
        media_type: str,
        width: int,
        height: int,
    ) -> bytes:
        if not _HEX_PATTERN.fullmatch(asset_hex):
            raise AssetStoreError("unknown asset identity")
        target = self._target(asset_hex, create_parent=False)
        if not target.is_file() or target.is_symlink():
            raise AssetStoreError("asset is unavailable")
        data = self._read_bounded(target)
        self._validate_bytes(asset_hex, media_type, width, height, data)
        return data

    def _target(self, asset_hex: str, *, create_parent: bool) -> Path:
        if not _HEX_PATTERN.fullmatch(asset_hex):
            raise AssetStoreError("unknown asset identity")
        parent = self._root / asset_hex[:2]
        if create_parent:
            parent.mkdir(exist_ok=True)
        if parent.exists() and parent.is_symlink():
            raise AssetStoreError("asset directory cannot be a symlink")
        resolved_parent = parent.resolve(strict=create_parent)
        if resolved_parent.parent != self._root:
            raise AssetStoreError("asset path escapes the configured root")
        return resolved_parent / f"{asset_hex}.webp"

    @staticmethod
    def _read_bounded(path: Path) -> bytes:
        with path.open("rb") as handle:
            data = handle.read(MAX_ASSET_BYTES + 1)
        if len(data) > MAX_ASSET_BYTES:
            raise AssetStoreError("asset exceeds the bounded size")
        return data

    @staticmethod
    def _validate_bytes(
        expected_hex: str,
        media_type: str,
        width: int,
        height: int,
        data: bytes,
    ) -> None:
        if media_type != "image/webp":
            raise AssetStoreError("asset media type is unsupported")
        if not data or len(data) > MAX_ASSET_BYTES:
            raise AssetStoreError("asset byte size is invalid")
        if hashlib.sha256(data).hexdigest() != expected_hex:
            raise AssetStoreError("asset hash verification failed")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != "WEBP":
                    raise AssetStoreError("asset format verification failed")
                if image.size != (width, height):
                    raise AssetStoreError("asset dimensions verification failed")
                image.load()
        except AssetStoreError:
            raise
        except (UnidentifiedImageError, OSError, ValueError):
            raise AssetStoreError("asset decode verification failed") from None


def _asset_hex(asset_id: str) -> str:
    match = _ASSET_PATTERN.fullmatch(asset_id)
    if match is None:
        raise AssetStoreError("asset identity is invalid")
    return match.group(1)
