from clinical_platform.contract import validate_row

VALID_ROW = {
    "source_url": "abfss://bronze-files@sa.dfs.core.windows.net/NG28_2022-11-30.pdf",
    "retrieved_at": "2024-01-01 00:00:00",
    "content_hash": "a" * 64,
    "guideline_version": "2022-11-30",
    "pipeline_run_id": "run-001",
    "ingest_timestamp": "2024-01-01 00:00:01",
    "guideline_id": "NG28",
    "length": 12345,
}


def test_valid_row_passes():
    assert validate_row(VALID_ROW) == []


def test_null_content_hash_flagged():
    row = {**VALID_ROW, "content_hash": None}
    reasons = validate_row(row)
    assert "NULL_PROVENANCE:content_hash" in reasons


def test_null_source_url_flagged():
    row = {**VALID_ROW, "source_url": None}
    assert "NULL_PROVENANCE:source_url" in validate_row(row)


def test_empty_pipeline_run_id_flagged():
    row = {**VALID_ROW, "pipeline_run_id": ""}
    assert "NULL_PROVENANCE:pipeline_run_id" in validate_row(row)


def test_invalid_hash_format():
    row = {**VALID_ROW, "content_hash": "not-a-sha256"}
    assert "INVALID_HASH_FORMAT" in validate_row(row)


def test_valid_sha256_passes():
    row = {**VALID_ROW, "content_hash": "b" * 64}
    assert "INVALID_HASH_FORMAT" not in validate_row(row)


def test_invalid_version_format_slash():
    row = {**VALID_ROW, "guideline_version": "30/11/2022"}
    assert "INVALID_VERSION_FORMAT" in validate_row(row)


def test_invalid_version_format_text():
    row = {**VALID_ROW, "guideline_version": "INVALID"}
    assert "INVALID_VERSION_FORMAT" in validate_row(row)


def test_valid_version_passes():
    row = {**VALID_ROW, "guideline_version": "2024-03-15"}
    assert "INVALID_VERSION_FORMAT" not in validate_row(row)


def test_zero_length_flagged():
    row = {**VALID_ROW, "length": 0}
    assert "EMPTY_CONTENT" in validate_row(row)


def test_none_length_flagged():
    row = {**VALID_ROW, "length": None}
    assert "EMPTY_CONTENT" in validate_row(row)


def test_empty_guideline_id_flagged():
    row = {**VALID_ROW, "guideline_id": ""}
    assert "INVALID_GUIDELINE_ID" in validate_row(row)


def test_lowercase_guideline_id_flagged():
    row = {**VALID_ROW, "guideline_id": "ng28"}
    assert "INVALID_GUIDELINE_ID" in validate_row(row)


def test_valid_guideline_ids():
    for gid in ("NG28", "QS209", "TA924", "PH38", "NG3"):
        row = {**VALID_ROW, "guideline_id": gid}
        assert "INVALID_GUIDELINE_ID" not in validate_row(row), f"Failed for {gid}"


def test_multiple_violations_all_returned():
    row = {**VALID_ROW, "content_hash": None, "length": 0, "guideline_version": "bad"}
    reasons = validate_row(row)
    assert "NULL_PROVENANCE:content_hash" in reasons
    assert "EMPTY_CONTENT" in reasons
    assert "INVALID_VERSION_FORMAT" in reasons
    assert len(reasons) >= 3
