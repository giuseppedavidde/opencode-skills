"""Private cache directories for the trading MCP server (DATA-20).

Every cache lives under ``$XDG_CACHE_HOME/trading_mcp`` (default
``~/.cache/trading_mcp``) in a directory with mode 0700. A directory or
file that belongs to another user, or that other users can write, is never
read: the cache then runs in memory only. Payloads are JSON (never pickle),
and writes are atomic (temp file in the same directory, ``fsync``,
``os.replace``) with mode 0600.

An explicit environment override (for example ``TRADING_DATA_CACHE_DIR``)
replaces the default location but gets the same checks.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

APP_DIR_NAME = "trading_mcp"
_DIR_MODE = 0o700
_UNSAFE_BITS = stat.S_IWGRP | stat.S_IWOTH


def _current_uid() -> int | None:
    getuid = getattr(os, "getuid", None)
    return getuid() if getuid is not None else None


def cache_root() -> Path | None:
    """Return ``$XDG_CACHE_HOME/trading_mcp`` or ``~/.cache/trading_mcp``.

    ``None`` when no home directory can be resolved (the caller then keeps
    its cache in memory). A relative ``XDG_CACHE_HOME`` is ignored, as the
    XDG specification requires.
    """
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg and os.path.isabs(xdg):
        return Path(xdg) / APP_DIR_NAME
    try:
        home = Path.home()
    except (RuntimeError, OSError, KeyError):
        return None
    if not str(home) or not home.is_absolute():
        return None
    return home / ".cache" / APP_DIR_NAME


def is_private(path: Path) -> bool:
    """True when ``path`` belongs to the current user and others cannot write it."""
    try:
        info = path.stat()
    except OSError:
        return False
    uid = _current_uid()
    if uid is not None and info.st_uid != uid:
        return False
    return not info.st_mode & _UNSAFE_BITS


def secure_dir(path: Path) -> Path | None:
    """Create ``path`` with mode 0700 and return it when it is private.

    Returns ``None`` (memory-only cache) when the directory cannot be
    created, belongs to another user or stays writable by others.
    """
    try:
        path.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
    except OSError as exc:
        logger.warning("Cache dir %s unavailable (%s); using memory only", path, type(exc).__name__)
        return None
    try:
        info = path.stat()
    except OSError:
        return None
    uid = _current_uid()
    if uid is not None and info.st_uid != uid:
        logger.warning("Cache dir %s belongs to uid %s, not %s; using memory only",
                       path, info.st_uid, uid)
        return None
    if stat.S_IMODE(info.st_mode) != _DIR_MODE:
        try:
            os.chmod(path, _DIR_MODE)
        except OSError:
            logger.warning("Cannot set mode 0700 on %s; using memory only", path)
            return None
    return path if is_private(path) else None


def cache_dir(name: str, env_var: str | None = None) -> Path | None:
    """Return the private cache directory ``name`` (or the ``env_var`` override).

    Args:
        name: Sub-directory under :func:`cache_root` (for example ``data``).
        env_var: Optional environment variable with an explicit directory.
    """
    override = os.environ.get(env_var, "").strip() if env_var else ""
    if override:
        target = Path(override).expanduser()
    else:
        root = cache_root()
        if root is None or secure_dir(root) is None:
            return None
        target = root / name
    if not target.is_absolute():
        logger.warning("Cache dir %s is not absolute; using memory only", target)
        return None
    return secure_dir(target)


def atomic_write_json(path: Path, payload: Any, *, default: Any = None, allow_nan: bool = True) -> bool:
    """Write ``payload`` as JSON to ``path`` atomically with mode 0600.

    Returns False (and logs) when the write fails; the caller keeps working
    from memory.
    """
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=default, ensure_ascii=False, allow_nan=allow_nan)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Cache write failed for %s: %s", path.name, type(exc).__name__)
        return False
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def read_json(path: Path) -> Any | None:
    """Read a JSON cache file, or ``None`` when absent, corrupt or not private."""
    if not path.exists():
        return None
    if not is_private(path):
        logger.warning("Ignoring cache file %s: not owned by this user or writable by others", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable cache file %s: %s", path.name, type(exc).__name__)
        return None
