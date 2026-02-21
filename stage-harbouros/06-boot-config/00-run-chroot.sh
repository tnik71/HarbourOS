#!/bin/bash -e
# Boot optimization and first-boot setup

echo "HarbourOS: Configuring boot..."

# Reduce GPU memory (headless server)
if ! grep -q "gpu_mem=" /boot/firmware/config.txt 2>/dev/null; then
    echo "gpu_mem=16" >> /boot/firmware/config.txt
fi

# Disable Bluetooth
if ! grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtoverlay=disable-bt" >> /boot/firmware/config.txt
fi

# Quiet boot
if [ -f /boot/firmware/cmdline.txt ]; then
    if ! grep -q "quiet" /boot/firmware/cmdline.txt; then
        sed -i 's/$/ quiet loglevel=3/' /boot/firmware/cmdline.txt
    fi
fi

# Install first-boot service
cp /tmp/harbouros-firstboot.service /etc/systemd/system/harbouros-firstboot.service
systemctl enable harbouros-firstboot.service

echo "HarbourOS: Boot configuration complete."
