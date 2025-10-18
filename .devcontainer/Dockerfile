# Devcontainer image for OKSI Software Licensing development
ARG VARIANT="3.11-bookworm"
FROM mcr.microsoft.com/devcontainers/python:${VARIANT}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        pkg-config \
        libssl-dev \
        libffi-dev \
        python3-venv \
        python3-dev \
        git \
        curl \
        wget \
        ca-certificates \
        unzip \
        zip \
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        qemu-user-static \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip

# Prepare workspace directories often used by tooling
RUN mkdir -p /workspaces && chown -R vscode:vscode /workspaces

ENV DEBIAN_FRONTEND=dialog
