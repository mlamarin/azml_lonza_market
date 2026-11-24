# azml_lonza_market

## Purpose

A small local sandbox that mimics, in simplified form, how a market-modelling data and ML stack could be organised on Azure. It is a learning and demonstration project, built to understand how the components fit together (ingestion, curation, training, validation, serving, interface, tests between components).

It is NOT a copy of any employer's real stack. Only public information about the target team is known, so the sandbox must never claim to reproduce it. Anything not reproduced must be stated plainly.

## Working rules

- Talk to the user in French. All code, comments, README text and documents are written in English.
- Never use the character "—" in generated text.
- Never invent figures, results or metrics. Data are synthetic and must be labelled as such.
- Prefer the simplest thing that runs. Ask before adding a new component.
- The project lives under /mnt/c/Users/marcl/work/projs/azml_lonza_market (Windows disk). Slower Docker I/O is accepted; use named volumes, not bind mounts, for container data.
- Tick items in PLAN.md as they are completed, and keep this file short and current.

## Decisions already taken

| Real-world component | Local stand-in | Note |
| --- | --- | --- |
| Azure Blob Storage (raw files) | Azurite container | Same API as Blob Storage |
| MongoDB or Cosmos DB for MongoDB (curated data) | MongoDB container | Code stays compatible with the Mongo API |
| Orchestration (Airflow or Data Factory) | Azure Functions run locally (Core Tools), blob trigger plus HTTP or timer trigger | Airflow deliberately left out to stay light |
| Azure ML (managed training and registry) | Python training script plus MLflow | No emulator exists for Azure ML, say so |
| MLflow | MLflow server container | Tracking and model registry |
| Prediction service | FastAPI container | Loads the promoted model from the MLflow registry |
| User interface | Streamlit container | Calls the FastAPI service |
| Microsoft Fabric | Not reproduced | Out of scope for a local sandbox |

Azurite emulates Blob, Queue and Table storage only. MongoDB is a separate container, not inside Azurite.

## Known limits to state honestly

- Azure Functions is a trigger for code, not a full orchestrator. No dependency graph or visual retry. In production this role would go to Data Factory or Durable Functions.
- Long training runs would be delegated to Azure ML in a real deployment.
- Data are synthetic, so model quality figures say nothing about real clinical progression.

## Demonstration scenario

1. A script generates a synthetic clinical-progression dataset and drops raw files into Azurite.
2. A blob-triggered function curates the data into MongoDB.
3. A function (HTTP-triggered for easy testing) trains a model, logs parameters and metrics to MLflow, including the Brier score and calibration data.
4. A validation step compares the new model with the current one (Brier score, reliability curve, aggregate test) and promotes it in the registry only if it is better.
5. FastAPI serves the promoted model. Streamlit shows probabilities and the calibration curve.
6. Contract tests check the data schema between ingestion and curation, and the API schema between FastAPI and Streamlit.

## Layout (target)

```
azml_lonza_market/
  CLAUDE.md
  PLAN.md
  docker-compose.yml        Azurite, MongoDB, MLflow, FastAPI, Streamlit
  src/azml_market/          installable package (src layout): settings, data generator, shared code
  scripts/                  standalone entry points only, no library code
  data/output/              generated files, not versioned
  functions/                Azure Functions app (curation, training, validation)
  api/                      FastAPI service
  ui/                       Streamlit app
  tests/                    unit and contract tests
```

## Commands (to fill in as they become real)

- Start the services: `docker compose up -d`
- Install the environment: `UV_LINK_MODE=copy uv sync` (installs `azml_market` in editable mode)
- Check the services: `uv run python scripts/check_infra.py`
- Generate, upload and plot the synthetic data: `uv run generate-data`, `uv run upload-data`, `uv run plot-data`
- Run the functions locally: `cd functions && source ../.venv/bin/activate && func start` (needs `functions/local.settings.json`, copied from `local.settings.example.json`). The host must use the project .venv so that `azml_market` is importable.
- Run the tests: `uv run pytest`
