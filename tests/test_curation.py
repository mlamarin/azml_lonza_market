"""Unit and contract tests for curation. No running service needed."""

import json

import pytest

from azml_market.curation.curate import curate_rows, parse_raw
from azml_market.data.generate import generate, write_outputs

VALID_ROW = {
    "record_id": "SYN-C0001-ONC-PI",
    "candidate_id": "SYN-C0001",
    "indication_area": "oncology",
    "modality": "cell_therapy",
    "from_phase": "I",
    "to_phase": "II",
    "sponsor_type": "biotech",
    "biomarker_selected": "True",
    "orphan_designation": "False",
    "start_year": "2012",
    "batch_id": "batch_01",
    "data_origin": "synthetic",
    "progressed": "1",
}


@pytest.fixture(scope="module")
def raw_files(tmp_path_factory):
    out = tmp_path_factory.mktemp("output")
    raw, truth = generate(seed=3, n_candidates=20)
    write_outputs(raw, truth, out, seed=3)
    return out / "raw"


# Contract: what the generator writes must satisfy the curation schema.
@pytest.mark.parametrize("suffix", ["csv", "json"])
def test_generator_output_satisfies_schema(raw_files, suffix):
    path = raw_files / f"batch_01.{suffix}"
    rows = parse_raw(path.read_bytes(), path.name)
    result = curate_rows(rows, source=path.name)
    assert result.rejected == []
    assert len(result.curated) == len(rows)


def test_csv_and_json_curate_to_same_documents(raw_files):
    docs = {}
    for suffix in ("csv", "json"):
        path = raw_files / f"batch_01.{suffix}"
        result = curate_rows(parse_raw(path.read_bytes(), path.name), source="same")
        docs[suffix] = [{k: v for k, v in d.items() if k != "_ingestion"} for d in result.curated]
    assert docs["csv"] == docs["json"]


def test_valid_row_is_typed_and_keyed_on_record_id():
    (doc,) = curate_rows([VALID_ROW], source="test.csv").curated
    assert doc["_id"] == "SYN-C0001-ONC-PI"
    assert doc["biomarker_selected"] is True
    assert doc["start_year"] == 2012
    assert doc["progressed"] == 1
    assert doc["_ingestion"]["source"] == "test.csv"


@pytest.mark.parametrize(
    "change, bad_field",
    [
        ({"from_phase": "IV"}, "from_phase"),
        ({"progressed": "2"}, "progressed"),
        ({"data_origin": "real"}, "data_origin"),
        ({"to_phase": "III"}, ""),  # cross-field rule: I must lead to II
        ({"unexpected": "x"}, "unexpected"),
    ],
)
def test_invalid_row_is_quarantined_with_reason(change, bad_field):
    row = {**VALID_ROW, **change}
    result = curate_rows([VALID_ROW, row], source="test.csv")
    assert len(result.curated) == 1
    (rejected,) = result.rejected
    assert rejected["_id"] == "test.csv#2"
    assert rejected["raw"] == row
    assert bad_field in [e["field"] for e in rejected["errors"]]


def test_missing_field_is_quarantined():
    row = {k: v for k, v in VALID_ROW.items() if k != "modality"}
    result = curate_rows([row], source="test.csv")
    assert result.curated == []
    assert result.rejected[0]["errors"][0]["field"] == "modality"


def test_json_not_flagged_synthetic_is_refused():
    content = json.dumps({"synthetic": False, "records": [VALID_ROW]}).encode()
    with pytest.raises(ValueError, match="not flagged as synthetic"):
        parse_raw(content, "batch.json")


def test_unsupported_file_type_is_refused():
    with pytest.raises(ValueError, match="unsupported file type"):
        parse_raw(b"", "batch.parquet")
