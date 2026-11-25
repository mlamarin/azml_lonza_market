"""Candidate models. Both take the same features and return a scikit-learn pipeline."""

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

CATEGORICAL = ["from_phase", "modality", "indication_area", "sponsor_type"]
BOOLEAN = ["biomarker_selected", "orphan_designation"]
FEATURES = CATEGORICAL + BOOLEAN
TARGET = "progressed"

MODEL_KINDS = ["logistic", "boosting"]


def build_model(kind: str, seed: int = 42) -> Pipeline:
    """logistic: additive model, like glm(family = binomial) on dummies.
    boosting: shallow gradient-boosted trees, can pick up interactions."""
    if kind == "logistic":
        estimator = LogisticRegression(max_iter=1000)
    elif kind == "boosting":
        estimator = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.1, max_iter=200, random_state=seed)
    else:
        raise ValueError(f"unknown model kind {kind!r}, expected one of {MODEL_KINDS}")
    preprocess = ColumnTransformer(
        [
            ("categories", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
            ("flags", "passthrough", BOOLEAN),
        ]
    )
    return Pipeline([("preprocess", preprocess), ("model", estimator)])
