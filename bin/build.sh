#!/usr/bin/env bash

# bin/build.sh: Build the project into a distributable form, including both any
#               compiling and/or packaging, e.g., Docker images.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

echo "🤖 ⟶  Building Docker image ${IMAGE_NAME} …"
eval "docker build \
        --pull \
        --build-arg VERSION=${VERSION} \
        --secret id=ARTIFACT_ACCESS_TOKEN \
        -t ${IMAGE_NAME} ."
