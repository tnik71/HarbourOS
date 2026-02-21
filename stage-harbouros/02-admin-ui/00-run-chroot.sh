#!/bin/bash -e
# Install HarbourOS Admin UI

echo "HarbourOS: Installing Admin UI..."

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

chmod 755 /etc/harbouros
chmod 644 /etc/harbouros/mounts.json
chmod 600 /etc/harbouros/admin.json

# Install systemd service
cp /tmp/admin-ui/../harbouros.service /etc/systemd/system/harbouros.service
systemctl enable harbouros.service

# Clean up staged files
rm -rf /tmp/admin-ui

echo "HarbourOS: Admin UI installed."
