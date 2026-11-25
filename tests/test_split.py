"""Unit tests for the train/test split."""

import pytest

from azml_market.data.generate import generate
from azml_market.training.split import margins, split_train_test


@pytest.fixture(scope="module")
def data():
    raw, _ = generate(seed=5, n_candidates=150)
    return raw, split_train_test(raw, seed=5)


def test_about_30_percent_test(data):
    _, split = data
    assert split.value_counts(normalize=True)["test"] == pytest.approx(0.30, abs=0.03)


def test_no_candidate_on_both_sides(data):
    raw, split = data
    assert (split.groupby(raw["candidate_id"]).nunique() == 1).all()


def test_phase_x_progressed_margins_are_similar(data):
    raw, split = data
    m = margins(raw, split)
    assert (m["train"] - m["test"]).abs().max() < 0.02


def test_same_seed_gives_same_split(data):
    raw, split = data
    assert split.equals(split_train_test(raw, seed=5))
