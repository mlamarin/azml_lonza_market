"""Train/test split of the curated transitions.

The split is stratified on from_phase x progressed, so both sides keep similar
margins, and grouped by candidate, so that the dependent transitions of one
candidate never sit on both sides (that would make the test score optimistic).
"""

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

N_FOLDS = 10
N_TEST_FOLDS = 3  # 3 folds out of 10: about 30 % test


def split_train_test(df: pd.DataFrame, seed: int = 42) -> pd.Series:
    """Return a Series aligned on df, with values "train" or "test"."""
    strata = df["from_phase"] + "_" + df["progressed"].astype(str)
    folds = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    split = pd.Series("train", index=df.index)
    for k, (_, test_idx) in enumerate(folds.split(df, strata, groups=df["candidate_id"])):
        if k < N_TEST_FOLDS:
            split.iloc[test_idx] = "test"
    return split


def margins(df: pd.DataFrame, split: pd.Series) -> pd.DataFrame:
    """Share of each from_phase x progressed cell, per side. For checking the split."""
    return (
        pd.crosstab([df["from_phase"], df["progressed"]], split, normalize="columns")
        .round(3)
        .rename_axis(columns=None)
    )
