#!/bin/bash -e
# Set up NAS mount infrastructure

echo "HarbourOS: Configuring NAS mount infrastructure..."

# Create base mount directory
mkdir -p /media/nas
chown plex:plex /media/nas

# Ensure the plex user can access mounted shares
usermod -aG plugdev plex 2>/dev/null || true

echo "HarbourOS: NAS mount infrastructure ready."
