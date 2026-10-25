# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
# Choose the LLM provider and database driver extras baked into the image,
# e.g. docker build --build-arg EXTRAS=openai,snowflake .
ARG EXTRAS=anthropic,databricks
WORKDIR /build
COPY pyproject.toml ./
COPY schema_scout ./schema_scout
RUN pip install --no-cache-dir --prefix=/install ".[${EXTRAS}]"

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 scout
COPY --from=builder /install /usr/local
WORKDIR /app
COPY settings.yaml ./
RUN mkdir erd_output && chown -R scout:scout /app
USER scout
ENV SCHEMA_SCOUT_ENV=production \
    PYTHONUNBUFFERED=1
# Credentials are NOT baked in: pass SCHEMA_SCOUT_DATABASE__PASSWORD and the LLM API key at runtime.
VOLUME ["/app/erd_output"]
ENTRYPOINT ["schema-scout"]
CMD ["--help"]
