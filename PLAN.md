# Plan

Work in this order. Run each step and confirm it works before starting the next. Tick the box when done.

## 0. Environment

- [x] Project folder: `/mnt/c/Users/marcl/work/projs/azml_lonza_market` (Windows disk, reached from WSL; slower Docker I/O accepted)
- [x] Opened in VS Code through the WSL extension
- [x] Docker running in WSL (`docker version` works) with the compose plugin (`docker compose version` works)
- [x] Python 3.12 and a virtual environment ready (`uv sync`, set `UV_LINK_MODE=copy` on /mnt/c)
- [x] Azure Functions Core Tools installed (`func --version` works)

## 1. Infrastructure containers

- [x] `docker-compose.yml` with Azurite, MongoDB and MLflow
- [x] Azurite reachable (blob endpoint answers)
- [x] MongoDB reachable (a test document can be inserted and read)
- [x] MLflow UI opens in the browser

## 2. Synthetic data

- [x] Script that generates a small synthetic dataset (candidates with phase, modality, indication and a progression outcome)
- [x] Script uploads the raw files to a container in Azurite
- [x] Data clearly labelled as synthetic

## 3. Curation function

- [x] Azure Functions app created in `functions/`
- [x] Blob-triggered function reads the raw file from Azurite
- [x] Cleaned records written to MongoDB
- [x] Schema check on the raw file (first contract test)

## 4. Training and validation

- [ ] HTTP-triggered function reads curated data and trains a simple model
- [ ] Parameters, metrics and the model logged to MLflow, including the Brier score
- [ ] Reliability curve data and an aggregate test computed and logged
- [ ] Validation step compares with the current registered model and promotes only if better

## 5. Serving and interface

- [ ] FastAPI service loads the promoted model from the registry and exposes a prediction endpoint
- [ ] Streamlit app calls the API and shows probabilities and the calibration curve
- [ ] Both services added to `docker-compose.yml`

## 6. Tests between components

- [ ] Unit tests for curation and metric functions
- [ ] Contract test on the API schema (FastAPI against what Streamlit expects)
- [ ] One end-to-end run from raw file to displayed prediction, scripted

## 7. Wrap-up

- [ ] Short README: what is reproduced, what is not (Azure ML, Fabric, full orchestration), how to run it
- [ ] Note what was learned and what would change in a real Azure deployment
