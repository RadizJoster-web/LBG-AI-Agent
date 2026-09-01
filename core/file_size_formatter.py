"""Bytes -> human-readable size string.

< 1 GB  -> "XXX MB"   (integer megabytes)
>= 1 GB -> "X.XX GB"  (two decimals)
"""
from __future__ import annotations

_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


def format_file_size(size_bytes: int | str | None) -> str | None:
    if size_bytes is None:
        return None
    try:
        size = int(size_bytes)
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None

    if size >= _GB:
        return f"{size / _GB:.2f} GB"
    if size >= _MB:
        return f"{round(size / _MB)} MB"
    if size >= _KB:
        return f"{max(1, round(size / _KB))} KB"
    return f"{size} B"
