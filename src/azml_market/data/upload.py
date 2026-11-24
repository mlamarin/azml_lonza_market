"""Upload the SYNTHETIC raw files and truth files to Azurite.

Raw files go to container "raw" (watched by the curation function).
Truth files go to container "reference", which is never curated nor used for training.

Run with: uv run upload-data [--format csv|json] [--batch batch_01]
"""

import argparse
from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContainerClient

from azml_market.settings import AZURITE_CONNECTION_STRING

RAW_CONTAINER = "raw"
REFERENCE_CONTAINER = "reference"
PREFIX = "clinical-progression"


def get_container(service: BlobServiceClient, name: str) -> ContainerClient:
    container = service.get_container_client(name)
    if not container.exists():
        container.create_container()
    return container


def upload_file(container: ContainerClient, path: Path) -> str:
    blob_name = f"{PREFIX}/{path.name}"
    with path.open("rb") as f:
        container.upload_blob(blob_name, f, overwrite=True, metadata={"synthetic": "true"})
    return blob_name


def main() -> None:
    parser = argparse.ArgumentParser(prog="upload-data", description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument("--batch", help="upload a single batch, e.g. batch_01 (default: all)")
    parser.add_argument("--data-dir", type=Path, default=Path("data/output"))
    args = parser.parse_args()

    pattern = f"{args.batch}" if args.batch else "batch_*"
    raw_files = sorted((args.data_dir / "raw").glob(f"{pattern}.{args.format}"))
    truth_files = sorted((args.data_dir / "truth").glob(f"{pattern}.csv"))
    if not raw_files:
        raise SystemExit(f"No raw files found in {args.data_dir / 'raw'}. Run generate-data first.")

    service = BlobServiceClient.from_connection_string(AZURITE_CONNECTION_STRING)
    raw_container = get_container(service, RAW_CONTAINER)
    reference_container = get_container(service, REFERENCE_CONTAINER)
    for path in raw_files:
        print(f"{RAW_CONTAINER}/{upload_file(raw_container, path)}")
    for path in truth_files:
        print(f"{REFERENCE_CONTAINER}/{upload_file(reference_container, path)}")


if __name__ == "__main__":
    main()
