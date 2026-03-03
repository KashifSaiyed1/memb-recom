#!/usr/bin/env bash
# exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Install Playwright and its system dependencies (the "drivers")
playwright install chromium
playwright install-deps chromium