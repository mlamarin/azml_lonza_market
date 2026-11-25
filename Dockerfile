# Development image shared by the api and ui services.
# Only the dependencies are installed in the image; the project is mounted on /app
# at run time (see docker-compose.yml), so code changes need no rebuild.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.12.5

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# azml_market is imported from the mounted source tree.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src
