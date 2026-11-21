FROM python:3.12-slim

WORKDIR /app
COPY . .

# pyswisseph has no cp312 wheel, so build it once and keep only libstdc++.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libstdc++6 \
    && pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "astro_mcp.server"]
