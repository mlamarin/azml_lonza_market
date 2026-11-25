"""Load the curated transitions (MongoDB) and the truth probabilities (Azurite)."""

import io

import pandas as pd
from azure.storage.blob import BlobServiceClient
from pymongo import MongoClient

from azml_market.curation.curate import CURATED_COLLECTION
from azml_market.data.upload import PREFIX, REFERENCE_CONTAINER
from azml_market.settings import AZURITE_CONNECTION_STRING, MONGO_DB, MONGO_URI


def load_transitions() -> pd.DataFrame:
    """All curated transitions, one row per record, sorted on record_id for a stable order."""
    collection = MongoClient(MONGO_URI)[MONGO_DB][CURATED_COLLECTION]
    df = pd.DataFrame(collection.find({}, {"_id": 0, "_ingestion": 0}))
    if df.empty:
        raise ValueError("No curated transitions in MongoDB. Upload raw files and run curation first.")
    return df.sort_values("record_id", ignore_index=True)


def load_truth() -> pd.DataFrame:
    """Truth probabilities (record_id, p_true). Diagnostic only, never used to fit or promote."""
    container = BlobServiceClient.from_connection_string(AZURITE_CONNECTION_STRING).get_container_client(
        REFERENCE_CONTAINER
    )
    frames = [
        pd.read_csv(io.BytesIO(container.download_blob(blob.name).readall()))
        for blob in container.list_blobs(name_starts_with=f"{PREFIX}/")
    ]
    return pd.concat(frames, ignore_index=True)
