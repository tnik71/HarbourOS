#!/bin/bash
set -euo pipefail

# HarbourOS Image Builder
# Clones pi-gen, injects custom stage, builds via Docker

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PI_GEN_DIR="${SCRIPT_DIR}/pi-gen-build"
PI_GEN_REPO="https://github.com/RPi-Distro/pi-gen.git"
PI_GEN_BRANCH="arm64"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "========================================="
echo "  HarbourOS Image Builder"
echo "========================================="

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Clone or update pi-gen
if [ -d "${PI_GEN_DIR}" ]; then
    echo "Using existing pi-gen directory..."
else
    echo "Cloning pi-gen..."
    git clone --depth 1 --branch "${PI_GEN_BRANCH}" "${PI_GEN_REPO}" "${PI_GEN_DIR}"
fi

# Copy config
echo "Copying HarbourOS configuration..."
cp "${SCRIPT_DIR}/pi-gen-config/config" "${PI_GEN_DIR}/config"

# Copy custom stage
echo "Copying stage-harbouros..."
rm -rf "${PI_GEN_DIR}/stage-harbouros"
cp -r "${SCRIPT_DIR}/stage-harbouros" "${PI_GEN_DIR}/stage-harbouros"

# Copy admin-ui into the stage
echo "Copying admin-ui into stage..."
mkdir -p "${PI_GEN_DIR}/stage-harbouros/02-admin-ui/files/admin-ui"
cp -r "${SCRIPT_DIR}/admin-ui/harbouros_admin" "${PI_GEN_DIR}/stage-harbouros/02-admin-ui/files/admin-ui/"
cp "${SCRIPT_DIR}/admin-ui/requirements.txt" "${PI_GEN_DIR}/stage-harbouros/02-admin-ui/files/admin-ui/"

# Copy config files into appropriate stage files directories
echo "Copying config files..."
cp "${SCRIPT_DIR}/config/harbouros.service" "${PI_GEN_DIR}/stage-harbouros/02-admin-ui/files/"
cp "${SCRIPT_DIR}/config/nftables.conf" "${PI_GEN_DIR}/stage-harbouros/05-security/files/"
cp "${SCRIPT_DIR}/config/sysctl-hardening.conf" "${PI_GEN_DIR}/stage-harbouros/05-security/files/"
cp "${SCRIPT_DIR}/config/avahi/harbouros.service" "${PI_GEN_DIR}/stage-harbouros/04-networking/files/"
cp "${SCRIPT_DIR}/config/harbouros-firstboot.service" "${PI_GEN_DIR}/stage-harbouros/06-boot-config/files/"
cp "${SCRIPT_DIR}/config/harbouros-plex-update.sh" "${PI_GEN_DIR}/stage-harbouros/01-plex-server/files/"
cp "${SCRIPT_DIR}/config/harbouros-plex-update.service" "${PI_GEN_DIR}/stage-harbouros/01-plex-server/files/"
cp "${SCRIPT_DIR}/config/harbouros-plex-update.timer" "${PI_GEN_DIR}/stage-harbouros/01-plex-server/files/"

# Skip desktop stages (3, 4, 5)
for stage in stage3 stage4 stage5; do
    if [ -d "${PI_GEN_DIR}/${stage}" ]; then
        touch "${PI_GEN_DIR}/${stage}/SKIP"
    fi
done

# Only export image after our custom stage
for stage in stage0 stage1 stage2; do
    touch "${PI_GEN_DIR}/${stage}/SKIP_IMAGES"
done
# Ensure our stage exports an image
rm -f "${PI_GEN_DIR}/stage-harbouros/SKIP_IMAGES"
touch "${PI_GEN_DIR}/stage-harbouros/EXPORT_IMAGE"

# Build via Docker
echo "Starting Docker build (this will take 30-60 minutes)..."
cd "${PI_GEN_DIR}"
./build-docker.sh

# Copy output
echo "Copying output image..."
mkdir -p "${OUTPUT_DIR}"
cp "${PI_GEN_DIR}"/deploy/*.img.xz "${OUTPUT_DIR}/" 2>/dev/null || \
cp "${PI_GEN_DIR}"/deploy/*.img "${OUTPUT_DIR}/" 2>/dev/null || \
echo "WARNING: No image found in deploy directory"

echo ""
echo "========================================="
echo "  Build complete!"
echo "  Image: ${OUTPUT_DIR}/"
echo "========================================="
echo ""
echo "Flash with: Raspberry Pi Imager or"
echo "  xzcat output/HarbourOS-*.img.xz | sudo dd of=/dev/diskN bs=4M"
