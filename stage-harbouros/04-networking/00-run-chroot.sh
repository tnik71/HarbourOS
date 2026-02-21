#!/bin/bash -e
# Configure networking and mDNS

echo "HarbourOS: Configuring networking..."

# Set hostname
echo "harbouros" > /etc/hostname
sed -i 's/127.0.1.1.*/127.0.1.1\tharbouros/' /etc/hosts

# Configure Avahi for mDNS (harbouros.local)
cp /tmp/avahi-harbouros.service /etc/avahi/services/harbouros.service 2>/dev/null || true

# Enable Avahi
systemctl enable avahi-daemon.service

echo "HarbourOS: Networking configured. Device will be accessible at harbouros.local"
