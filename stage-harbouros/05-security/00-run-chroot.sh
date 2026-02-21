#!/bin/bash -e
# Security hardening

echo "HarbourOS: Applying security hardening..."

# Install nftables firewall rules
cp /tmp/nftables.conf /etc/nftables.conf
systemctl enable nftables.service

# Install sysctl hardening
cp /tmp/sysctl-hardening.conf /etc/sysctl.d/99-harbouros.conf

# SSH hardening
sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config

# Disable unused services
systemctl disable bluetooth.service 2>/dev/null || true
systemctl disable triggerhappy.service 2>/dev/null || true
systemctl disable apt-daily-upgrade.timer 2>/dev/null || true
systemctl disable apt-daily.timer 2>/dev/null || true

echo "HarbourOS: Security hardening applied."
