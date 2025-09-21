# Minimal image to run the OKSI License CLI in interactive mode

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code
COPY scripts/ ./scripts/

# Ensure the token directory exists (can be replaced by a bind mount)
RUN mkdir -p /app/.oksi

# Default to interactive mode; pass other args to override at runtime
ENTRYPOINT ["python", "scripts/oksi_license_cli.py"]
CMD ["--interactive"]

