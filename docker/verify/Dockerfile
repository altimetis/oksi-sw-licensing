# Minimal container to run OKSI License CLI verify
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy CLI sources
COPY scripts/ /app/scripts/

# Ensure entrypoint script is executable
RUN chmod +x /app/scripts/verify-entrypoint.sh

# Default command: run verify and print success/failure message based on exit code
ENTRYPOINT ["/app/scripts/verify-entrypoint.sh"]
