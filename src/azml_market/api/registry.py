"""Access to the MLflow model registry for the API.

An alias such as "champion" is resolved on every request, so an approval takes
effect without restarting the API. Loaded models are cached by version number:
an MLflow model version never changes once registered.
"""

import io

import mlflow
import mlflow.artifacts
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException
from sklearn.pipeline import Pipeline

from azml_market.settings import MLFLOW_TRACKING_URI
from azml_market.training.pipeline import MODEL_NAME


class UnknownModel(LookupError):
    pass


class ModelRegistry:
    def __init__(self) -> None:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        self.client = MlflowClient()
        self._models: dict[str, Pipeline] = {}

    def resolve(self, ref: str) -> ModelVersion:
        """A version number ("2") or an alias ("champion") to a registered model version."""
        try:
            if ref.isdigit():
                return self.client.get_model_version(MODEL_NAME, ref)
            return self.client.get_model_version_by_alias(MODEL_NAME, ref)
        except MlflowException:
            raise UnknownModel(f"No model version or alias {ref!r} for {MODEL_NAME!r}") from None

    def load(self, version: ModelVersion) -> Pipeline:
        if version.version not in self._models:
            self._models[version.version] = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{version.version}")
        return self._models[version.version]

    def list_versions(self) -> list[dict]:
        aliases: dict[str, list[str]] = {}
        for alias, version in self.client.get_registered_model(MODEL_NAME).aliases.items():
            aliases.setdefault(version, []).append(alias)
        rows = []
        for v in self.client.search_model_versions(f"name = '{MODEL_NAME}'"):
            run = self.client.get_run(v.run_id)
            rows.append(
                {
                    "version": v.version,
                    "model_kind": run.data.params.get("model_kind", "unknown"),
                    "aliases": sorted(aliases.get(v.version, [])),
                    "validation_status": v.tags.get("validation_status"),
                    "validation_reason": v.tags.get("validation_reason"),
                    "test_brier": run.data.metrics.get("test_brier"),
                    "test_spiegelhalter_p": run.data.metrics.get("test_spiegelhalter_p"),
                }
            )
        return sorted(rows, key=lambda r: int(r["version"]))

    def model_kind(self, version: ModelVersion) -> str:
        return self.client.get_run(version.run_id).data.params.get("model_kind", "unknown")

    def calibration(self, version: ModelVersion) -> dict:
        """Reliability curves and metrics logged with the training run."""
        run = self.client.get_run(version.run_id)

        def curve(name: str) -> list[dict]:
            text = mlflow.artifacts.load_text(f"runs:/{version.run_id}/calibration/{name}")
            return pd.read_csv(io.StringIO(text)).to_dict(orient="records")

        return {
            "model_version": version.version,
            "model_kind": run.data.params.get("model_kind", "unknown"),
            "test_brier": run.data.metrics["test_brier"],
            "test_spiegelhalter_p": run.data.metrics["test_spiegelhalter_p"],
            "truth_oracle_brier": run.data.metrics["truth_oracle_brier"],
            "model_curve": curve("reliability.csv"),
            "truth_curve": curve("reliability_truth.csv"),
        }
