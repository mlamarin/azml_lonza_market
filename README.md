# azml_lonza_market

A small local sandbox that mimics, in simplified form, how a market-modelling data and ML stack could be organised on Azure: ingestion, curation, training, validation, serving, interface, and tests between components.

It is a learning and demonstration project. It is **not** a copy of any company's real stack: only public information about such teams was available, and nothing here claims to reproduce an actual system.

**All data are synthetic.** They are generated from a known model with arbitrary coefficients. Any model quality figure obtained here says nothing about real clinical progression.

## Status

| Step | Content | State |
| --- | --- | --- |
| 0 | Environment (Docker, uv, Azure Functions Core Tools) | Done |
| 1 | Infrastructure containers (Azurite, MongoDB, MLflow) | Done |
| 2 | Synthetic data generator and upload to Azurite | Done |
| 3 | Curation function (blob trigger to MongoDB) | Done |
| 4 | Training and validation (MLflow, Brier score, promotion) | In progress |
| 5 | Serving (FastAPI) and interface (Streamlit) | To do |
| 6 | Unit, contract and end-to-end tests | To do |

See [PLAN.md](PLAN.md) for the detailed checklist.

## Architecture

| Real-world component | Local stand-in |
| --- | --- |
| Azure Blob Storage (raw files) | Azurite container (same Blob API) |
| MongoDB or Cosmos DB for MongoDB (curated data) | MongoDB container |
| Orchestration (Data Factory, Airflow) | Azure Functions run locally with Core Tools |
| Azure ML (managed training and registry) | Python training code plus MLflow |
| Prediction service | FastAPI container (planned) |
| User interface | Streamlit container (planned) |

```
synthetic generator --> Azurite "raw" --> curation function --> MongoDB
                                                                  |
                     Streamlit <-- FastAPI <-- MLflow registry <-- training + validation
```

## What is not reproduced

- **Azure ML**: no local emulator exists. Training runs as plain Python and logs to MLflow. In a real deployment, long training runs would go to Azure ML.
- **Full orchestration**: Azure Functions trigger code but offer no dependency graph or visual retry. In production this role would go to Data Factory or Durable Functions.
- **Microsoft Fabric**: out of scope for a local sandbox.
- **Security, networking, identity**: local emulators use public development keys and no authentication.

## The synthetic dataset

One row is one **phase transition** of one **candidate-indication pair**, for example candidate `SYN-C0012` in oncology moving from Phase II to Phase III.

- Each pair starts at Phase I and attempts transitions in sequence until the first failure, so a pair yields one to three dependent rows.
- The outcome `progressed` is drawn from a logistic model on phase, modality, indication area, biomarker selection, orphan designation and sponsor type, plus one interaction. The coefficients are arbitrary illustrative values defined in [generate.py](src/azml_market/data/generate.py), not published success rates.
- The true probability `p_true` of each row is written to a separate truth file. It is never given to the model and serves as ground truth when checking calibration.
- Data come in four batches. `batch_04` has a different covariate mix (more cell and gene therapies, more biomarker-selected trials) under the same truth model.
- Every record carries `data_origin = "synthetic"`, the JSON files carry `"synthetic": true`, and every blob has the metadata `synthetic=true`.

Fields: `record_id`, `candidate_id`, `indication_area`, `modality`, `from_phase`, `to_phase`, `sponsor_type`, `biomarker_selected`, `orphan_designation`, `start_year`, `batch_id`, `data_origin`, `progressed`.

## Curation

The blob-triggered function `curate_raw_blob` ([functions/function_app.py](functions/function_app.py)) fires for every file under `raw/clinical-progression/` and calls [curate.py](src/azml_market/curation/curate.py):

- Each row is checked against the schema contract in [schema.py](src/azml_market/curation/schema.py) (allowed values, types, `to_phase` following `from_phase`, no unknown column).
- Valid rows become one MongoDB document per transition in `market.transitions`, with `_id = record_id` and an `_ingestion` block (source file, timestamp, schema version).
- Invalid rows go one by one to `market.rejected`, with the raw row and the reasons. The rest of the file is still curated.
- Writes are upserts on `_id`, so replaying a batch, in CSV or in JSON, leaves the same final state.
- The truth file in container `reference` is never read by curation.

How the Functions host, the blob trigger and its receipts work is explained in [functions/README.md](functions/README.md).

## Training and validation

Code in [src/azml_market/training/](src/azml_market/training/), exposed as HTTP functions and as commands.

- **Data**: curated transitions from MongoDB. Split 70 % train, 30 % test, stratified on `from_phase` x `progressed` and grouped by candidate, so that a candidate's dependent transitions never sit on both sides.
- **Models**: `logistic` (logistic regression on one-hot categories, like `glm(family = binomial)`) or `boosting` (shallow gradient-boosted trees). Features: phase, modality, indication area, sponsor type, biomarker selection, orphan designation.
- **Logged to MLflow** (experiment `clinical-progression`): parameters, test Brier score, Spiegelhalter calibration test (z and p-value), reliability curve (CSV and PNG), test predictions, and the model, registered as a new version of `clinical-progression`.
- **Truth diagnostics**: because the data are synthetic, the run also logs the mean absolute gap between predictions and `p_true`, and the Brier score of `p_true` itself (the best any model could do on that test set). These are never used to fit or to promote.
- **Validation**: the new version is scored on the same test set as the current `champion`. It passes if its Brier score is lower and the Spiegelhalter test does not reject its calibration (p >= 0.05). A passing version gets the alias `challenger`; the outcome and reason are stored as version tags.
- **Approval**: a human call to `approve` moves the `champion` alias to the challenger. Only versions with `validation_status = passed` can be approved.

```bash
uv run train-model --model logistic          # or: curl -X POST "http://localhost:7071/api/train?model=logistic"
uv run approve-model                         # or: curl -X POST "http://localhost:7071/api/approve"
```

### Two ways to start training, one code path

Both entry points call the same function, `train_and_validate()` in [pipeline.py](src/azml_market/training/pipeline.py). Only the trigger differs:

| Trigger | What the caller needs |
| --- | --- |
| `uv run train-model` | The repository, the Python environment, and network access to MongoDB, Azurite and MLflow |
| `POST /api/train` | Any HTTP client (`curl`, a browser, another service) that can reach the Functions host |

MLflow does not start training: it records what the training code sends to it (parameters, metrics, artifacts, models). In both cases our code trains, then writes to MLflow.

The HTTP route lets any client start a training run without Python or uv (a Streamlit button, a scheduler, Data Factory), keeps connection settings on the host side, and returns a JSON contract (model version, metrics, verdict). In Azure it can also be restricted with a function key or Entra ID, which matters most for `approve`. The call is synchronous: the request waits for training to finish, which is fine for this small dataset but not for real training (see [functions/README.md](functions/README.md#http-functions)).

## Getting started

Requirements: Docker with the compose plugin, [uv](https://docs.astral.sh/uv/), Azure Functions Core Tools v4.

```bash
# Python environment (Python 3.12)
export UV_LINK_MODE=copy          # needed when the project sits on /mnt/c under WSL
uv sync

# Infrastructure
docker compose up -d
uv run python scripts/check_infra.py

# Synthetic data
uv run generate-data --seed 42     # writes data/output/raw and data/output/truth
uv run upload-data                 # raw files to container "raw", truth to "reference"
uv run plot-data                   # PNGs in data/output/plots

# Curation (Azure Functions, local host)
cp functions/local.settings.example.json functions/local.settings.json
cd functions && source ../.venv/bin/activate && func start
# each file landing in raw/clinical-progression/ is curated into MongoDB

# Tests
uv run pytest
```

`upload-data` accepts `--format csv|json` and `--batch batch_01` to send a single batch.

Service endpoints:

| Service | Address |
| --- | --- |
| Azurite Blob | http://localhost:10000 |
| MongoDB | mongodb://localhost:27017 |
| MLflow UI | http://localhost:5000 |

Settings are read from environment variables with local defaults, see [settings.py](src/azml_market/settings.py) and [.env.example](.env.example).

## Layout

```
src/azml_market/          installable Python package (src layout)
    settings.py           connection settings shared by all code
    data/                 synthetic data generator, upload and plots
scripts/                  standalone entry points (infrastructure checks)
tests/                    unit tests
data/output/              generated files, not versioned
functions/                Azure Functions app (curation)
api/                      FastAPI service (planned)
ui/                       Streamlit app (planned)
```

`uv sync` installs the package in editable mode, so `import azml_market` works from tests, scripts and services, and the commands `generate-data`, `upload-data` and `plot-data` are available through `uv run`.
