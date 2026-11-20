"""JSON encoding of OHLCV frames and vendor dicts for the disk cache (no pickle)."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def jsonable(value: Any, _depth: int = 0) -> Any:
    """Convert numpy, pandas and datetime values into plain JSON values.

    Non-finite floats become ``None``; unknown objects become their string.
    """
    if _depth > 20:
        return None
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item, _depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item, _depth + 1) for item in value]
    if isinstance(value, np.ndarray):
        return [jsonable(item, _depth + 1) for item in value.tolist()]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def encode_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Encode a DatetimeIndex frame as a JSON-safe dict (timezone preserved)."""
    index = frame.index
    tz = str(index.tz) if isinstance(index, pd.DatetimeIndex) and index.tz is not None else None
    columns = [str(col) for col in frame.columns]
    data: dict[str, list[Any]] = {}
    for col, name in zip(frame.columns, columns):
        data[name] = [jsonable(item) for item in frame[col].tolist()]
    return {
        "index": [ts.isoformat() for ts in index],
        "index_name": index.name,
        "tz": tz,
        "columns": columns,
        "dtypes": {name: str(frame[col].dtype) for col, name in zip(frame.columns, columns)},
        "data": data,
    }


def decode_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Rebuild a frame encoded by :func:`encode_frame`.

    Raises:
        ValueError: When the payload is malformed.
    """
    try:
        raw_index = payload["index"]
        columns = list(payload["columns"])
        data = payload["data"]
        tz = payload.get("tz")
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed frame payload") from exc
    if tz:
        index = pd.DatetimeIndex(pd.to_datetime(raw_index, utc=True)).tz_convert(tz)
    else:
        index = pd.DatetimeIndex(pd.to_datetime(raw_index))
    index.name = payload.get("index_name")
    frame = pd.DataFrame({col: data[col] for col in columns}, index=index)
    dtypes = payload.get("dtypes") or {}
    for col in columns:
        wanted = str(dtypes.get(col, ""))
        if "int" in wanted and not frame[col].isna().any():
            frame[col] = frame[col].astype("int64")
        elif "float" in wanted or "int" in wanted:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    if len(frame) != len(raw_index):
        raise ValueError("frame length mismatch")
    return frame
