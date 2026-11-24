"""Azure Functions app (Python v2 programming model).

curate_raw_blob fires when a file lands under raw/clinical-progression/ in
Blob Storage (Azurite locally) and curates it into MongoDB.
"""

import logging

import azure.functions as func
from pymongo import MongoClient

from azml_market.curation.curate import curate_blob
from azml_market.settings import MONGO_DB, MONGO_URI

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
