FROM node:22-bookworm-slim AS apify_runtime
RUN npm install --global apify-cli@1.12.0

FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=apify_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=apify_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/apify-cli/dist/apify.js /usr/local/bin/apify

# Build/install this checkout, including the bundled manifest and output schema.
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY trace_them ./trace_them
COPY .actor ./.actor
RUN pip install --no-cache-dir . && trace-them --version
ENTRYPOINT ["python", "/app/.actor/run_actor.py"]
