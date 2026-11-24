"""Check that the infrastructure containers (Azurite, MongoDB, MLflow) answer.

Run with: uv run python scripts/check_infra.py
Exit code is non-zero if any service fails.
"""

import os
import sys
import uuid

import requests
from azure.storage.blob import BlobServiceClient
from pymongo import MongoClient

AZURITE_CONNECTION_STRING = os.environ.get(
    "AZURITE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")


def check_azurite() -> None:
    service = BlobServiceClient.from_connection_string(AZURITE_CONNECTION_STRING)
    container = service.get_container_client("healthcheck")
    if not container.exists():
        container.create_container()
    payload = b"ping"
    blob = container.get_blob_client(f"ping-{uuid.uuid4().hex}.txt")
    blob.upload_blob(payload)
    assert blob.download_blob().readall() == payload
    blob.delete_blob()


def check_mongo() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    collection = client["healthcheck"]["ping"]
    doc_id = collection.insert_one({"ping": "pong"}).inserted_id
    assert collection.find_one({"_id": doc_id})["ping"] == "pong"
    collection.delete_one({"_id": doc_id})


def check_mlflow() -> None:
    response = requests.get(f"{MLFLOW_TRACKING_URI}/health", timeout=5)
    response.raise_for_status()


def main() -> int:
    checks = {"Azurite": check_azurite, "MongoDB": check_mongo, "MLflow": check_mlflow}
    failed = False
    for name, check in checks.items():
        try:
            check()
            print(f"OK    {name}")
        except Exception as exc:
            failed = True
            print(f"FAIL  {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
