"""Curate a raw file into MongoDB.

Pure functions (parse, validate) are kept apart from the MongoDB write, so the
logic can be unit tested without any running service. The Azure Function only
calls curate_blob.

Choices:
- one MongoDB document per transition, _id = record_id, collection "transitions";
- invalid rows are quarantined one by one in collection "rejected", with the reason;
- writes are upserts, so replaying a batch (in CSV or JSON) gives the same final state.
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import ValidationError
from pymongo import ReplaceOne
from pymongo.database import Database

from azml_market.curation.schema import SCHEMA_VERSION, TransitionRecord

CURATED_COLLECTION = "transitions"
REJECTED_COLLECTION = "rejected"


@dataclass
class CurationResult:
    source: str
    curated: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def parse_raw(content: bytes, blob_name: str) -> list[dict]:
    """Read a raw CSV or JSON file into a list of string-keyed rows."""
    suffix = PurePosixPath(blob_name).suffix.lower()
    text = content.decode("utf-8")
    if suffix == ".csv":
        return list(csv.DictReader(io.StringIO(text)))
    if suffix == ".json":
        document = json.loads(text)
        if document.get("synthetic") is not True:
            raise ValueError(f"{blob_name}: JSON file is not flagged as synthetic")
        return document["records"]
    raise ValueError(f"{blob_name}: unsupported file type {suffix!r}")


def curate_rows(rows: list[dict], source: str, now: datetime | None = None) -> CurationResult:
    """Validate each row against the schema. Valid rows become curated documents."""
    now = now or datetime.now(UTC)
    ingestion = {"source": source, "ingested_at": now, "schema_version": SCHEMA_VERSION}
    result = CurationResult(source=source)
    for row_number, row in enumerate(rows, start=1):
        try:
            record = TransitionRecord.model_validate(row)
        except ValidationError as exc:
            result.rejected.append(
                {
                    "_id": f"{source}#{row_number}",
                    "source": source,
                    "row_number": row_number,
                    "raw": row,
                    "errors": [
                        {"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
                    ],
                    "rejected_at": now,
                }
            )
            continue
        document = record.model_dump()
        document["_id"] = record.record_id
        document["_ingestion"] = ingestion
        result.curated.append(document)
    return result


def write_result(db: Database, result: CurationResult) -> None:
    """Upsert curated and rejected documents, keyed on _id."""
    for collection, documents in (
        (CURATED_COLLECTION, result.curated),
        (REJECTED_COLLECTION, result.rejected),
    ):
        if documents:
            db[collection].bulk_write(
                [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in documents], ordered=False
            )


def curate_blob(content: bytes, blob_name: str, db: Database) -> CurationResult:
    """Parse, validate and write one raw file. Returns what was curated and rejected."""
    result = curate_rows(parse_raw(content, blob_name), source=blob_name)
    write_result(db, result)
    return result
