"""Unit tests for ScratchProvisioner scratch-related methods."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.backend.agent.errors.kernel import (
    MkfsError,
    ScratchFileCreationError,
    ScratchMountError,
    ScratchUmountError,
)
from ai.backend.agent.stage.kernel_lifecycle.docker.scratch import ScratchProvisioner
from ai.backend.common.exception import BackendAIError
from ai.backend.common.types import KernelId

_KERNEL_ID = KernelId(uuid.UUID("00000000-0000-0000-0000-000000000001"))
_MODULE = "ai.backend.agent.stage.kernel_lifecycle.docker.scratch"


def _stat_with_blocks(blocks: int) -> Callable[..., Any]:
    """Return a Path.stat replacement that calls os.stat but overrides st_blocks.

    Because the wrapper delegates to the real os.stat, FileNotFoundError is
    still propagated for non-existing paths, so Path.exists() keeps working
    correctly during tests.
    """

    def _wrapper(self: Path, *, follow_symlinks: bool = True) -> MagicMock:
        real = os.stat(str(self), follow_symlinks=follow_symlinks)
        m = MagicMock()
        m.st_blocks = blocks
        m.st_size = real.st_size
        m.st_ino = real.st_ino
        m.st_mode = real.st_mode
        return m

    return _wrapper


class TestExceptionHierarchy:
    """Verify the new exception classes are BackendAIError subclasses."""

    def test_scratch_file_creation_error_is_backendai_error(self) -> None:
        assert issubclass(ScratchFileCreationError, BackendAIError)

    def test_mkfs_error_is_backendai_error(self) -> None:
        assert issubclass(MkfsError, BackendAIError)

    def test_scratch_mount_error_is_backendai_error(self) -> None:
        assert issubclass(ScratchMountError, BackendAIError)

    def test_scratch_umount_error_is_backendai_error(self) -> None:
        assert issubclass(ScratchUmountError, BackendAIError)


class TestCreateSparseFile:
    """Tests for ScratchProvisioner._create_sparse_file."""

    @pytest.fixture
    def provisioner(self) -> ScratchProvisioner:
        return ScratchProvisioner()

    def test_unlinks_preexisting_file_and_succeeds(
        self, provisioner: ScratchProvisioner, tmp_path: Path
    ) -> None:
        """Pre-existing file with content is unlinked; a fresh empty file is created."""
        filepath = tmp_path / "test.img"
        filepath.write_bytes(b"existing content" * 100)

        with (
            patch(f"{_MODULE}.os.truncate"),
            patch.object(Path, "stat", _stat_with_blocks(0)),
        ):
            # Should not raise; the pre-existing file is unlinked and a fresh one is created.
            provisioner._create_sparse_file(str(filepath), 1024 * 1024)

        # After context exit the real stat is restored.
        # os.truncate was mocked (no-op), so the file is the 0-byte file left by touch().
        assert filepath.exists()
        assert filepath.stat().st_size == 0

    def test_raises_when_blocks_nonzero(
        self, provisioner: ScratchProvisioner, tmp_path: Path
    ) -> None:
        """ScratchFileCreationError is raised when the freshly created file has allocated blocks."""
        filepath = tmp_path / "test.img"

        with (
            patch(f"{_MODULE}.os.truncate"),
            patch.object(Path, "stat", _stat_with_blocks(8)),
        ):
            with pytest.raises(ScratchFileCreationError):
                provisioner._create_sparse_file(str(filepath), 1024 * 1024)


class TestCreateLoopFilesystem:
    """Tests for ScratchProvisioner._create_loop_filesystem."""

    @pytest.fixture
    def provisioner(self) -> ScratchProvisioner:
        return ScratchProvisioner()

    def _make_process_mock(self, exit_code: int) -> AsyncMock:
        proc = AsyncMock()
        proc.wait = AsyncMock(return_value=exit_code)
        return proc

    async def test_mkfs_failure_raises_mkfs_error_and_cleans_up(
        self, provisioner: ScratchProvisioner, tmp_path: Path
    ) -> None:
        """When mkfs.ext4 returns non-zero, MkfsError is raised and scratch_dir is removed."""
        failing_mkfs = self._make_process_mock(1)

        with (
            patch(f"{_MODULE}.os.truncate"),
            patch.object(Path, "stat", _stat_with_blocks(0)),
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=failing_mkfs)),
        ):
            with pytest.raises(MkfsError):
                await provisioner._create_loop_filesystem(tmp_path, 1024 * 1024, _KERNEL_ID)

        scratch_dir = tmp_path / str(_KERNEL_ID)
        assert not scratch_dir.exists()

    async def test_mount_failure_raises_scratch_mount_error_and_cleans_up(
        self, provisioner: ScratchProvisioner, tmp_path: Path
    ) -> None:
        """When mount returns non-zero, ScratchMountError is raised and scratch_dir is removed."""
        successful_mkfs = self._make_process_mock(0)
        failing_mount = self._make_process_mock(1)

        with (
            patch(f"{_MODULE}.os.truncate"),
            patch.object(Path, "stat", _stat_with_blocks(0)),
            patch(
                "asyncio.create_subprocess_exec",
                AsyncMock(side_effect=[successful_mkfs, failing_mount]),
            ),
        ):
            with pytest.raises(ScratchMountError):
                await provisioner._create_loop_filesystem(tmp_path, 1024 * 1024, _KERNEL_ID)

        scratch_dir = tmp_path / str(_KERNEL_ID)
        assert not scratch_dir.exists()
