# Postgres 17 + pgvector, built on the same base image (Debian trixie / glibc)
# as plain postgres:17 so existing data volumes keep identical collations.
# (The official pgvector/pgvector:pg17 image is Debian bookworm — different
# glibc — so it is only used for throwaway databases such as CI.)
FROM postgres:17
RUN apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-${PG_MAJOR}-pgvector" \
    && rm -rf /var/lib/apt/lists/*
