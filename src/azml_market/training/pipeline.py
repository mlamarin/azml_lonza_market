"""Train, validate and approve models, with MLflow tracking and registry.

Workflow:
1. train_and_validate fits a model, logs it to MLflow and registers a new version.
2. The new version is compared with the current "champion" on the same test set.
   It passes if its Brier score is lower AND the Spiegelhalter test does not reject
   its calibration. A passing version gets the alias "challenger"; nothing else changes.
3. approve moves the alias "champion" to the challenger. This is the human approval step.

The truth p_true is logged as a diagnostic only. Fitting and promotion use observed outcomes.
"""

import argparse
import json
from datetime import UTC, datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature

from azml_market.settings import MLFLOW_TRACKING_URI
from azml_market.training.data import load_transitions, load_truth
from azml_market.training.metrics import brier_score, evaluate, reliability_curve
from azml_market.training.models import FEATURES, MODEL_KINDS, TARGET, build_model
from azml_market.training.split import split_train_test

EXPERIMENT = "clinical-progression"
MODEL_NAME = "clinical-progression"
CHAMPION = "champion"
CHALLENGER = "challenger"
ALPHA = 0.05  # Spiegelhalter test level


def _client() -> MlflowClient:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient()


def _champion_version(client: MlflowClient) -> str | None:
    try:
        return client.get_model_version_by_alias(MODEL_NAME, CHAMPION).version
    except MlflowException:
        return None


def _reliability_figure(curves: dict[str, pd.DataFrame]):
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfect calibration")
    for label, curve in curves.items():
        ax.plot(curve["mean_predicted"], curve["observed_rate"], marker="o", label=label)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed progression rate")
    ax.set_title("Reliability curve on test set (synthetic data)")
    ax.legend()
    fig.tight_layout()
    return fig


def train_and_validate(kind: str = "logistic", seed: int = 42) -> dict:
    """Fit, log and register a model, then validate it against the champion."""
    client = _client()
    mlflow.set_experiment(EXPERIMENT)

    df = load_transitions().merge(load_truth(), on="record_id", how="left", validate="one_to_one")
    split = split_train_test(df, seed=seed)
    train, test = df[split == "train"], df[split == "test"]

    model = build_model(kind, seed=seed).fit(train[FEATURES], train[TARGET])
    p_test = model.predict_proba(test[FEATURES])[:, 1]
    metrics = evaluate(test[TARGET], p_test)
    curve = reliability_curve(test[TARGET], p_test)
    truth_curve = reliability_curve(test[TARGET], test["p_true"])

    with mlflow.start_run(run_name=kind) as run:
        mlflow.set_tag("data_origin", "synthetic")
        mlflow.log_params(
            {"model_kind": kind, "seed": seed, "n_train": len(train), "n_test": len(test), "features": ",".join(FEATURES)}
        )
        mlflow.log_metrics({f"test_{k}": v for k, v in metrics.items()})
        # Diagnostics against the truth, available only because the data are synthetic.
        mlflow.log_metrics(
            {
                "truth_mean_abs_error": float((p_test - test["p_true"]).abs().mean()),
                "truth_oracle_brier": brier_score(test[TARGET], test["p_true"]),
            }
        )
        mlflow.log_text(curve.to_csv(index=False), "calibration/reliability.csv")
        mlflow.log_text(truth_curve.to_csv(index=False), "calibration/reliability_truth.csv")
        fig = _reliability_figure({kind: curve, "truth p_true": truth_curve})
        mlflow.log_figure(fig, "calibration/reliability.png")
        plt.close(fig)
        predictions = test[["record_id", "from_phase", TARGET, "p_true"]].assign(p_predicted=p_test)
        mlflow.log_text(predictions.to_csv(index=False), "calibration/test_predictions.csv")
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            signature=infer_signature(test[FEATURES], p_test),
            registered_model_name=MODEL_NAME,
        )

    (version,) = client.search_model_versions(f"run_id = '{run.info.run_id}'")
    decision = _validate(client, version.version, test, metrics)
    return {"run_id": run.info.run_id, "model_kind": kind, "version": version.version, "metrics": metrics, **decision}


def _validate(client: MlflowClient, version: str, test: pd.DataFrame, metrics: dict) -> dict:
    """Compare the new version with the champion on the same test set and tag the outcome."""
    champion = _champion_version(client)
    calibration_ok = metrics["spiegelhalter_p"] >= ALPHA
    champion_brier = None
    if champion is None:
        better = True
    else:
        champion_model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{CHAMPION}")
        champion_brier = brier_score(test[TARGET], champion_model.predict_proba(test[FEATURES])[:, 1])
        better = metrics["brier"] < champion_brier

    passed = calibration_ok and better
    reasons = []
    if not better:
        reasons.append(f"Brier {metrics['brier']:.4f} not lower than champion v{champion} ({champion_brier:.4f})")
    if not calibration_ok:
        reasons.append(f"Spiegelhalter p = {metrics['spiegelhalter_p']:.3f} < {ALPHA}")
    reason = "; ".join(reasons) or (
        "no champion yet" if champion is None else f"better than champion v{champion} ({champion_brier:.4f})"
    )

    tags = {
        "validation_status": "passed" if passed else "failed",
        "validation_reason": reason,
        "compared_with": f"v{champion}" if champion else "none",
    }
    for key, value in tags.items():
        client.set_model_version_tag(MODEL_NAME, version, key, value)
    if passed:
        client.set_registered_model_alias(MODEL_NAME, CHALLENGER, version)
    return {"validation": tags["validation_status"], "reason": reason, "champion_brier": champion_brier}


def approve(version: str | None = None) -> dict:
    """Human approval: make the challenger (or a given passed version) the champion."""
    client = _client()
    if version is None:
        try:
            version = client.get_model_version_by_alias(MODEL_NAME, CHALLENGER).version
        except MlflowException:
            raise ValueError("No challenger to approve.") from None
    try:
        status = client.get_model_version(MODEL_NAME, version).tags.get("validation_status")
    except MlflowException:
        raise ValueError(f"Version {version} of model {MODEL_NAME!r} does not exist.") from None
    if status != "passed":
        raise ValueError(f"Version {version} has validation_status={status!r}, only passed versions can be approved.")
    previous = _champion_version(client)
    client.set_registered_model_alias(MODEL_NAME, CHAMPION, version)
    client.set_model_version_tag(MODEL_NAME, version, "approved_at", datetime.now(UTC).isoformat())
    try:
        if client.get_model_version_by_alias(MODEL_NAME, CHALLENGER).version == version:
            client.delete_registered_model_alias(MODEL_NAME, CHALLENGER)
    except MlflowException:
        pass
    return {"champion": version, "previous_champion": previous}


def train_cli() -> None:
    parser = argparse.ArgumentParser(prog="train-model", description="Train, register and validate a model")
    parser.add_argument("--model", choices=MODEL_KINDS, default="logistic")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train_and_validate(args.model, args.seed), indent=2))


def approve_cli() -> None:
    parser = argparse.ArgumentParser(prog="approve-model", description="Approve a validated model as champion")
    parser.add_argument("--version", help="model version to approve (default: current challenger)")
    args = parser.parse_args()
    print(json.dumps(approve(args.version), indent=2))
