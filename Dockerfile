FROM python:3.12-slim AS builder
WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY trace_them ./trace_them
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="Trace Them"
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels trace-them \
    && rm -rf /wheels \
    && useradd --create-home traceuser
USER traceuser
WORKDIR /home/traceuser
ENTRYPOINT ["trace-them"]
