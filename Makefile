SHELL := /usr/bin/env bash

# Maintainer/Developer Makefile for OKSI Software Licensing
# - Build native fingerprint helper
# - Package Python CLI bundle
# - Stage and serve a local release for testing the installer
# - Install to a temporary prefix/root for validation

PY ?= python3
CMAKE ?= cmake
PORT ?= 8000
BASE ?= http://localhost:$(PORT)
PREFIX ?= $(PWD)/tmp/usr/local
ROOT ?= $(PWD)/tmp/opt/oksi
SUDO ?= sudo

.PHONY: help
help:
	@echo "Targets:"
	@echo "  venv                  Create .venv and install requirements"
	@echo "  run-cli ARGS=...      Run CLI via source tree (uses .venv)"
	@echo "  build-fingerprint     Build native oksi_fingerprint (CMake)"
	@echo "  clean-fingerprint     Remove fingerprint build dir"
	@echo "  dist-python           Package Python bundle (tar.gz)"
	@echo "  dist-fingerprint      Build and stage native helper into dist/bin"
	@echo "  dist-all              Build both bundles"
	@echo "  release-stage         Stage local release tree under dist/release"
	@echo "  serve-release         Serve dist/release on :$(PORT)"
	@echo "  install-local         Install using local server into tmp prefixes"
	@echo "  uninstall-local       Uninstall from tmp prefixes"
	@echo "  clean                 Remove build/, dist/, tmp/"
	@echo "  gh-check              Verify GitHub CLI and auth"
	@echo "  gh-tag                Create/push annotated tag VERSION"
	@echo "  gh-release            Build dist + create GitHub Release and upload assets"
	@echo "Variables: PY, CMAKE, PORT, BASE, PREFIX, ROOT, SUDO, VERSION, TARGETS, REPO"

.PHONY: venv
venv:
	$(PY) -m venv .venv
	. .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

.PHONY: run-cli
run-cli:
	@if [ ! -d .venv ]; then echo "Create venv first: make venv" >&2; exit 1; fi
	. .venv/bin/activate && PYTHONPATH=src $(PY) src/sw-licensing/cli.py $(ARGS)

.PHONY: build-fingerprint
build-fingerprint:
	$(CMAKE) -S src/fingerprint -B build/fingerprint -DCMAKE_BUILD_TYPE=Release
	$(CMAKE) --build build/fingerprint --config Release -- -j
	@echo "Built: build/fingerprint/bin/oksi_fingerprint"

.PHONY: clean-fingerprint
clean-fingerprint:
	rm -rf build/fingerprint

.PHONY: dist-python
dist-python:
	bash scripts/distribution/make-python-bundle.sh

.PHONY: dist-fingerprint
dist-fingerprint:
	# Set TARGETS="linux-amd64 linux-arm64" to cross-compile if toolchains exist
	TARGETS="$(TARGETS)" bash scripts/distribution/make-fingerprint.sh

.PHONY: dist-all
dist-all: dist-python dist-fingerprint

.PHONY: release-stage
release-stage: dist-all
	@mkdir -p dist/release/bin
	cp scripts/distribution/install.sh dist/release/install.sh
	cp dist/oksi-sw-licensing-python.tar.gz dist/release/
	OS=$$(uname -s | tr '[:upper:]' '[:lower:]'); \
	ARCH=$$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/'); \
	cp dist/bin/oksi_fingerprint-$$OS-$$ARCH dist/release/bin/ || true; \
	echo "Staged: dist/release (BASE=$(BASE))"

.PHONY: serve-release
serve-release: release-stage
	cd dist/release && $(PY) -m http.server $(PORT)

.PHONY: install-local
install-local: release-stage
	@mkdir -p $(PREFIX)/bin $(ROOT)
	@echo "Installing locally to PREFIX=$(PREFIX) ROOT=$(ROOT) from $(BASE) ..."
	$(SUDO) bash scripts/distribution/install.sh --base "$(BASE)" --prefix "$(PREFIX)" --root "$(ROOT)"
	@echo "Installed CLI: $(PREFIX)/bin/oksi-sw-license"
	@echo "Installed FP:  $(PREFIX)/bin/oksi_fingerprint (if available)"
	@echo "Manifest:      $(ROOT)/sw-licensing/manifest.txt"

.PHONY: uninstall-local
uninstall-local:
	@echo "Uninstalling from PREFIX=$(PREFIX) ROOT=$(ROOT) ..."
	$(SUDO) "$(PREFIX)/bin/oksi-sw-license-uninstall" || true

.PHONY: clean
clean: clean-fingerprint
	rm -rf dist tmp build

# ----------------------
# GitHub Releases (gh)
# ----------------------

# GitHub repository in owner/name form. Auto-detect when possible; override as needed.
# - Falls back to parsing origin URL if gh isn't configured.
# - You can override by passing REPO=org/name to make.
REPO ?= $(shell gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || \
  git remote get-url origin 2>/dev/null | sed -E 's#(git@|https://)([^/:]+)[:/]([^/]+)/([^/.]+)(\\.git)?#\3/\4#' || echo unknown/unknown)

.PHONY: require-version
require-version:
	@if [ -z "$(strip $(VERSION))" ]; then echo "VERSION is required. Fix: rerun 'make $(firstword $(MAKECMDGOALS)) VERSION=v1.2.3' with the desired tag." >&2; exit 1; fi

.PHONY: gh-check
gh-check:
	@gh --version >/dev/null 2>&1 || { echo "GitHub CLI 'gh' not found. Install from https://cli.github.com/" >&2; exit 1; }
	@gh auth status

.PHONY: gh-tag
gh-tag: require-version
	@if git rev-parse "$(VERSION)" >/dev/null 2>&1; then \
	  echo "Tag $(VERSION) already exists"; \
	else \
	  git tag -a "$(VERSION)" -m "Release $(VERSION)"; \
	  git push origin "$(VERSION)"; \
	fi


.PHONY: gh-release
gh-release: require-version
	@$(MAKE) gh-check
	@$(MAKE) gh-tag
	@$(MAKE) dist-all
	@echo "Creating GitHub Release $(VERSION) and uploading assets..."
	@ASSETS=( \
	  scripts/distribution/install.sh \
	  scripts/distribution/uninstall.sh \
	  dist/oksi-sw-licensing-python.tar.gz \
	  $$(ls dist/bin/oksi_fingerprint-* 2>/dev/null || true) \
	); \
	set -e; \
	gh release create -R "$(REPO)" "$(VERSION)" --title "OKSI SW Licensing $(VERSION)" --notes "Distribution release $(VERSION)" "$${ASSETS[@]}" || { \
	  echo "If the release exists, use: gh release upload $(VERSION) <assets> --clobber"; exit 1; }
	@echo "Marking as latest..."; gh release edit -R "$(REPO)" "$(VERSION)" --latest
	@echo "Done. Download base (latest): https://github.com/$(REPO)/releases/latest/download";
