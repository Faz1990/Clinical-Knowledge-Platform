from __future__ import annotations

from .config import ACCEPTED_CLINICAL_AREAS


def validate_scope(row: dict) -> list[str]:
    """
    Semantic scope gate — requires manifest join to have run first.

    Two distinct failure classes:
      MISSING_MANIFEST_ENTRY  — no manifest row matched this document (uncatalogued)
      INVALID_CLINICAL_AREA   — document is catalogued but out of platform scope

    Placement: after manifest join in Silver, before PDF parse.
    Signal only exists post-join, so cannot be evaluated at the structural gate.
    """
    reasons: list[str] = []
    area = row.get("expected_clinical_area")
    if area is None or area == "":
        reasons.append("MISSING_MANIFEST_ENTRY")
    elif area not in ACCEPTED_CLINICAL_AREAS:
        reasons.append("INVALID_CLINICAL_AREA")
    return reasons
