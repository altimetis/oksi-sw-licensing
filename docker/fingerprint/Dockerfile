# Simple image to run scripts/fingerprint.py
# Usage:
#   docker build -t oksi/fingerprint -f docker/fingerprint/Dockerfile .
#   docker run --rm \
#     oksi/fingerprint

FROM python:3.12-slim

WORKDIR /app

# Copy only what's needed
COPY scripts/fingerprint.py /app/fingerprint.py

# Environment: allow explicit override when running
ENV PYTHONUNBUFFERED=1

# Default command prints the fingerprint
CMD ["python", "/app/fingerprint.py"]

