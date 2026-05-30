from __future__ import annotations

# Platform scope — what this system accepts.
# Changing this is a deliberate governance decision: update here, commit, and the
# semantic gate enforces the new scope on the next pipeline run. git blame is the audit trail.
ACCEPTED_CLINICAL_AREAS: frozenset[str] = frozenset({"type_2_diabetes"})

# Controlled vocabulary of all known clinical-area values.
# A value that appears in the manifest but is not here is an unrecognised label —
# treated as INVALID_CLINICAL_AREA at the gate (cannot be in-scope if unrecognised).
CLINICAL_AREA_VOCABULARY: frozenset[str] = frozenset({
    "type_2_diabetes",
    "type_1_diabetes",
    "diabetes_children",
    "diabetes_pregnancy",
    "hypertension",
    "ckd",
})
