from clinical_platform.scope import validate_scope


def test_type2_diabetes_passes():
    assert validate_scope({"expected_clinical_area": "type_2_diabetes"}) == []


def test_ng17_type1_quarantined():
    reasons = validate_scope({"expected_clinical_area": "type_1_diabetes"})
    assert reasons == ["INVALID_CLINICAL_AREA"]


def test_ng3_pregnancy_quarantined():
    assert validate_scope({"expected_clinical_area": "diabetes_pregnancy"}) == [
        "INVALID_CLINICAL_AREA"
    ]


def test_ng18_children_quarantined():
    assert validate_scope({"expected_clinical_area": "diabetes_children"}) == [
        "INVALID_CLINICAL_AREA"
    ]


def test_null_area_is_missing_manifest():
    assert validate_scope({"expected_clinical_area": None}) == ["MISSING_MANIFEST_ENTRY"]


def test_empty_area_is_missing_manifest():
    assert validate_scope({"expected_clinical_area": ""}) == ["MISSING_MANIFEST_ENTRY"]


def test_unrecognised_area_is_invalid():
    # Typo or unknown label — not in vocabulary, not in-scope
    assert validate_scope({"expected_clinical_area": "type2_diabetes"}) == ["INVALID_CLINICAL_AREA"]


def test_missing_key_treated_as_missing_manifest():
    assert validate_scope({}) == ["MISSING_MANIFEST_ENTRY"]
