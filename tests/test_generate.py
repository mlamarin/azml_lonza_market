"""Unit tests for the synthetic data generator."""

import json

import pandas as pd
import pytest

from data.generate import RAW_COLUMNS, generate, write_outputs


@pytest.fixture(scope="module")
def generated():
    return generate(seed=1, n_candidates=30)


def test_raw_has_expected_columns(generated):
    raw, _ = generated
    assert list(raw.columns) == RAW_COLUMNS


def test_record_ids_are_unique(generated):
    raw, _ = generated
    assert raw["record_id"].is_unique


def test_outcome_is_binary_and_data_labelled_synthetic(generated):
    raw, _ = generated
    assert set(raw["progressed"]) <= {0, 1}
    assert (raw["data_origin"] == "synthetic").all()


def test_truth_matches_raw(generated):
    raw, truth = generated
    assert truth["record_id"].tolist() == raw["record_id"].tolist()
    assert truth["p_true"].between(0, 1, inclusive="neither").all()


def test_transitions_stop_at_first_failure(generated):
    raw, _ = generated
    for _, pair in raw.groupby(["candidate_id", "indication_area"]):
        # Every transition except the last one of a pair must have progressed.
        assert pair["progressed"].iloc[:-1].eq(1).all()


def test_same_seed_gives_same_data():
    raw_a, truth_a = generate(seed=7, n_candidates=10)
    raw_b, truth_b = generate(seed=7, n_candidates=10)
    pd.testing.assert_frame_equal(raw_a, raw_b)
    pd.testing.assert_frame_equal(truth_a, truth_b)


def test_csv_and_json_hold_same_records(generated, tmp_path):
    raw, truth = generated
    write_outputs(raw, truth, tmp_path, seed=1)
    from_csv = pd.read_csv(tmp_path / "raw" / "batch_01.csv")
    document = json.loads((tmp_path / "raw" / "batch_01.json").read_text())
    from_json = pd.DataFrame(document["records"])
    assert document["synthetic"] is True
    pd.testing.assert_frame_equal(from_csv, from_json, check_dtype=False)
