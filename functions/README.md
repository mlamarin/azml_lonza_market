# Azure Functions in this sandbox

This folder holds the Azure Functions app that curates raw files into MongoDB. It runs locally with Azure Functions Core Tools (`func`), against Azurite instead of a real storage account. All data it handles are synthetic.

## Core ideas

An Azure Function is a piece of code that runs when an **event** happens. You do not write a server or a polling loop: you declare what should start your code (a **trigger**), and the runtime does the rest.

| Concept | Meaning | Here |
| --- | --- | --- |
| Function app | A deployable unit grouping several functions, sharing settings and a storage account | this `functions/` folder |
| Function | One Python function plus its trigger | `curate_raw_blob` |
| Trigger | The event that starts a function: new blob, HTTP request, timer, queue message... | blob trigger on `raw/clinical-progression/{name}` |
| Binding | A declarative input or output connection (the trigger is a special input binding) | the blob, passed as `func.InputStream` |
| Programming model v2 | Triggers and bindings declared with Python decorators in `function_app.py`, no `function.json` files | used here |

### Host and worker

Running `func start` launches two processes:

```
func (host, .NET)               reads host.json and settings, watches triggers,
 |                              decides when to run a function, handles retries and logs
 +-- python worker.py           imports function_app.py and executes your code on request
```

The host and the worker talk over gRPC. Your code never polls Azurite: the host detects a new blob, reads it, and hands it to the function as an argument. The same split exists in Azure, where the host is managed by the platform.

## Files

| File | Role | Versioned |
| --- | --- | --- |
| `function_app.py` | The functions and their trigger decorators | yes |
| `host.json` | Host configuration: logging level, extension bundle version | yes |
| `local.settings.example.json` | Template for local settings | yes |
| `local.settings.json` | Local settings, read as environment variables by the host and the code | no (may hold secrets) |
| `requirements.txt` | Packages needed by the functions in a real deployment | yes |
| `.funcignore` | Files left out when publishing to Azure | yes |

The **extension bundle** declared in `host.json` is a package of trigger and binding extensions (Blob, Queue, HTTP, Timer...) downloaded by the host on first start. It avoids installing each extension by hand.

### Settings

`local.settings.json` (copied from the example):

| Key | Meaning |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME` | Language worker to start: `python` |
| `AzureWebJobsStorage` | Storage account used by the host. `UseDevelopmentStorage=true` is a shortcut for Azurite on its default ports |
| `MONGO_URI`, `MONGO_DB` | Read by `azml_market.settings` to reach MongoDB |

`AzureWebJobsStorage` plays two roles here: it is the account the blob trigger watches (through `connection="AzureWebJobsStorage"` in the decorator), and the account where the host keeps its own state (see below). In Azure, the `Values` of this file become the **App settings** of the Function App.

## Running it

Prerequisites: `docker compose up -d` (Azurite and MongoDB running) and `uv sync` at the project root.

```bash
cd functions
cp local.settings.example.json local.settings.json   # first time only
source ../.venv/bin/activate                         # the worker must see azml_market
func start                                           # add --verbose to see every storage call
```

The host lists the functions it found:

```
Functions:
	curate_raw_blob: blobTrigger
```

Then drop a file into the watched path, for example `uv run upload-data --batch batch_01` from the project root, and watch the log lines:

```
Executing 'Functions.curate_raw_blob' (Reason='New blob detected(LogsAndContainerScan): raw/clinical-progression/batch_01.csv', ...)
Curated raw/clinical-progression/batch_01.csv: 586 records written, 0 rejected
Executed 'Functions.curate_raw_blob' (Succeeded, ...)
```

Stop the host with `Ctrl+C`. Only one host can listen on port 7071 at a time.

## How the blob trigger decides what to process

Nothing in our code says "run again when a file changes". This comes from the blob trigger itself:

1. The host scans the watched container periodically.
2. Each blob has an **ETag**, a version identifier that changes on every write.
3. For each blob, the host looks for a **blob receipt** for that exact ETag. If none exists, it runs the function, then writes the receipt.

So:

- a new blob is processed once;
- an overwritten blob gets a new ETag and is processed again;
- a deleted blob triggers nothing, and its curated documents stay in MongoDB;
- deleting the receipts forces every blob to be processed again on the next scan.

What happens to the data on a second run is our decision, not the host's: curation upserts on `record_id` (`ReplaceOne(..., upsert=True)` in [curate.py](../src/azml_market/curation/curate.py)), so replaying a file gives the same final state instead of duplicates.

### Where the host keeps its state

The host creates these containers in the `AzureWebJobsStorage` account (Azurite here) on first start:

```
azure-webjobs-hosts/
  blobreceipts/<host id>/Host.Functions.curate_raw_blob/<ETag>/raw/clinical-progression/batch_01.csv
  locks/<host id>/host                                  one active host at a time
  locks/<host id>/WebJobs.Internal.Blobs.Listener       one blob listener at a time
azure-webjobs-secrets/                                  host and function keys
```

Receipts are never cleaned up automatically. The 404 errors logged on the very first start are the host checking for these containers before creating them, and are expected.

### Failures

If the function raises an exception, the host retries it. After several failed attempts (5 by default) the blob is reported to the poison queue `webjobs-blobtrigger-poison` in the same storage account, and is no longer retried. Invalid rows do not raise: they are quarantined in MongoDB collection `rejected` and the rest of the file is curated. Only a file-level problem (unsupported extension, JSON not flagged as synthetic, MongoDB unreachable) makes the function fail.

## Observing the host

| What | How |
| --- | --- |
| Live logs | the terminal running `func start` (`--verbose` for storage calls) |
| Host state | `curl -s http://localhost:7071/admin/host/status` |
| Functions and their triggers | `curl -s http://localhost:7071/admin/functions` |
| Receipts, locks, poison queue | Azure Storage Explorer, Emulator account, container `azure-webjobs-hosts` and queues |
| Processes | `ps -ef \| grep -E "func\|worker.py"` |
| Result | MongoDB collections `market.transitions` and `market.rejected` |

Locally the admin API needs no key. In Azure it is protected by the host keys stored in `azure-webjobs-secrets`.

## Code layout

`function_app.py` stays thin: it receives the blob and calls `curate_blob` from the `azml_market` package. Parsing, schema validation and the MongoDB write live in [src/azml_market/curation/](../src/azml_market/curation/), where they are unit tested without any running service (`uv run pytest`).

## Differences with a real Azure deployment

- **Packaging**: locally the worker uses the project `.venv`, where `azml_market` is installed in editable mode. A deployment would also need to ship `azml_market` (built wheel or vendored code); `requirements.txt` alone is not enough.
- **Trigger latency**: the classic blob trigger relies on scanning and logs. On large containers, or on an idle Consumption plan, detection can take minutes. In Azure, the recommended option is the Event Grid based blob trigger (`source="EventGrid"`), which reacts to storage events instead.
- **Orchestration**: Functions start code on events but offer no dependency graph or visual retry. A real pipeline would use Data Factory or Durable Functions for that role.
- **Security**: Azurite uses the public development key and no network isolation. In Azure, the function would reach storage and the database through managed identities and private networking.
- **Monitoring**: logs here go to the terminal. In Azure they go to Application Insights.
