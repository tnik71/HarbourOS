#!/bin/bash -e
# Install HarbourOS Admin UI

echo "HarbourOS: Installing Admin UI..."

# Create harbouros system user (no login shell, no home directory)
if ! id -u harbouros >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin harbouros
fi

# Create application directory
mkdir -p /opt/harbouros
cp -r /tmp/admin-ui/* /opt/harbouros/

# Create Python virtual environment and install dependencies
python3 -m venv /opt/harbouros/venv
/opt/harbouros/venv/bin/pip install --no-cache-dir -r /opt/harbouros/requirements.txt

# Create config directory
mkdir -p /etc/harbouros
echo '{"mounts": []}' > /etc/harbouros/mounts.json

# Create default admin auth config (password: "harbouros")
HASH=$(/opt/harbouros/venv/bin/python3 -c "import bcrypt; print(bcrypt.hashpw(b'harbouros', bcrypt.gensalt()).decode())")
cat > /etc/harbouros/admin.json << EOFAUTH
{
  "password_hash": "${HASH}",
  "password_changed": false
}
EOFAUTH

chown harbouros:harbouros /etc/harbouros
chmod 755 /etc/harbouros
chown harbouros:harbouros /etc/harbouros/mounts.json
chmod 644 /etc/harbouros/mounts.json
chown harbouros:harbouros /etc/harbouros/admin.json
chmod 600 /etc/harbouros/admin.json

# Install sudoers file for harbouros user
cp /tmp/admin-ui/../harbouros-sudoers /etc/sudoers.d/harbouros
chmod 440 /etc/sudoers.d/harbouros

# Install systemd service
cp /tmp/admin-ui/../harbouros.service /etc/systemd/system/harbouros.service
systemctl enable harbouros.service

# Clean up staged files
rm -rf /tmp/admin-ui

echo "HarbourOS: Admin UI installed."
