#!/bin/bash -e
# Security hardening

echo "HarbourOS: Applying security hardening..."

# Install sysctl hardening
cp /tmp/sysctl-hardening.conf /etc/sysctl.d/99-harbouros.conf

# SSH hardening
sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config
sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config

# fail2ban for SSH brute-force protection
cp /tmp/fail2ban-sshd.conf /etc/fail2ban/jail.d/sshd.conf
systemctl enable fail2ban.service 2>/dev/null || true

# Plex log rotation
cp /tmp/logrotate-plex.conf /etc/logrotate.d/plex

# Disable unused services
systemctl disable bluetooth.service 2>/dev/null || true
systemctl disable triggerhappy.service 2>/dev/null || true
systemctl disable apt-daily-upgrade.timer 2>/dev/null || true
systemctl disable apt-daily.timer 2>/dev/null || true

echo "HarbourOS: Security hardening applied."
