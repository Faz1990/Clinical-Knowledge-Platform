from __future__ import annotations

import os
import re

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GUIDELINE_ID = re.compile(r"^[A-Z]+\d+$")

_PROVENANCE_COLS = (
    "source_url",
    "retrieved_at",
    "content_hash",
    "guideline_version",
    "pipeline_run_id",
    "ingest_timestamp",
)


def validate_row(row: dict) -> list[str]:
    """Return reason codes for a Bronze row; empty list means the row passes the contract."""
    reasons: list[str] = []

    for col in _PROVENANCE_COLS:
        val = row.get(col)
        if val is None or val == "":
            reasons.append(f"NULL_PROVENANCE:{col}")

    ch = row.get("content_hash") or ""
    if ch and not _SHA256.match(ch):
        reasons.append("INVALID_HASH_FORMAT")

    gv = row.get("guideline_version") or ""
    if gv and not _DATE.match(gv):
        reasons.append("INVALID_VERSION_FORMAT")

    length = row.get("length")
    if length is None or length <= 0:
        reasons.append("EMPTY_CONTENT")

    gid = row.get("guideline_id") or ""
    if not gid or not _GUIDELINE_ID.match(gid):
        reasons.append("INVALID_GUIDELINE_ID")

    return reasons
