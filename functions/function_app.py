"""Azure Functions app (Python v2 programming model).

curate_raw_blob fires when a file lands under raw/clinical-progression/ in
Blob Storage (Azurite locally) and curates it into MongoDB.
train (POST /api/train?model=logistic|boosting) trains, registers and validates a model.
approve (POST /api/approve[?version=N]) is the human approval step: challenger -> champion.
"""

import json
import logging

import azure.functions as func
from pymongo import MongoClient

from azml_market.curation.curate import curate_blob
from azml_market.settings import MONGO_DB, MONGO_URI

# azml_market.training (MLflow, scikit-learn) is imported inside the HTTP functions:
# importing it at module level is slow enough for the host to give up indexing.

app = func.FunctionApp()

# One client per worker process, reused across invocations.
mongo_client = MongoClient(MONGO_URI)


@app.blob_trigger(arg_name="blob", path="raw/clinical-progression/{name}", connection="AzureWebJobsStorage")
def curate_raw_blob(blob: func.InputStream) -> None:
    result = curate_blob(blob.read(), blob.name, mongo_client[MONGO_DB])
    logging.info(
        "Curated %s: %d records written, %d rejected",
        blob.name,
        len(result.curated),
        len(result.rejected),
    )


def _json(body: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body), status_code=status_code, mimetype="application/json")


# Anonymous access is for local testing only. In Azure these would use function keys or Entra ID.
@app.route(route="train", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def train(req: func.HttpRequest) -> func.HttpResponse:
    from azml_market.training.pipeline import train_and_validate

    try:
        result = train_and_validate(kind=req.params.get("model", "logistic"))
    except ValueError as exc:
        return _json({"error": str(exc)}, status_code=400)
    logging.info("Trained %s as version %s: %s", result["model_kind"], result["version"], result["validation"])
    return _json(result)


@app.route(route="approve", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def approve_model(req: func.HttpRequest) -> func.HttpResponse:
    from azml_market.training.pipeline import approve

    try:
        result = approve(req.params.get("version"))
    except ValueError as exc:
        return _json({"error": str(exc)}, status_code=400)
    logging.info("Approved version %s as champion", result["champion"])
    return _json(result)
