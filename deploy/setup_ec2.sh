#!/usr/bin/env bash
# deploy/setup_ec2.sh — Automated Zero-Cost Provisioning for AWS EC2 (Ubuntu 22.04 LTS Free Tier)
set -euo pipefail

echo "======================================================================"
echo " Shortlist Resume Screening Assistant — AWS EC2 Free Tier Provisioner"
echo "======================================================================"

# 1. Verify root / sudo
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run this script with sudo: sudo ./deploy/setup_ec2.sh"
  exit 1
fi

# 2. Configure 2GB Swap Space (Crucial for 1GB RAM t2.micro / t3.micro to prevent OOM)
echo "[+] Step 1/6: Checking and configuring 2GB swap space for EC2 Free Tier..."
if ! swapon --show | grep -q "/swapfile"; then
  echo "    Creating /swapfile (2GB)..."
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
  echo "    Swap created successfully:"
  free -h
else
  echo "    Swap space already active:"
  free -h
fi

# 3. Update packages and install Docker prerequisites
echo "[+] Step 2/6: Updating system packages and installing prerequisites..."
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw

# 4. Install Docker CE and Docker Compose Plugin
echo "[+] Step 3/6: Installing Docker Engine and Docker Compose..."
if ! command -v docker &> /dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable docker
  systemctl start docker
  echo "    Docker installed: $(docker --version)"
else
  echo "    Docker already installed: $(docker --version)"
fi

# 5. Configure Firewall (UFW)
echo "[+] Step 4/6: Configuring firewall rules..."
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable
echo "    Firewall status:"
ufw status verbose

# 6. Check .env and GROQ_API_KEY
echo "[+] Step 5/6: Configuring application environment..."
if [ ! -f .env ]; then
  if [ -n "${GROQ_API_KEY:-}" ]; then
    echo "GROQ_API_KEY=${GROQ_API_KEY}" > .env
    echo "    Created .env from environment variable."
  else
    echo ""
    read -rp "Enter your Groq API Key (starts with gsk_): " user_groq_key
    echo "GROQ_API_KEY=${user_groq_key}" > .env
    echo "    Created .env with provided key."
  fi
else
  echo "    Found existing .env file."
fi

# 7. Build and launch Docker Compose stack
echo "[+] Step 6/6: Building and launching containers (PostgreSQL, Backend, Frontend/Nginx)..."
docker compose down --remove-orphans || true
docker compose up -d --build

echo "======================================================================"
echo " DEPLOYMENT COMPLETE!"
echo "======================================================================"
PUBLIC_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "<YOUR-EC2-PUBLIC-IP>")
echo ""
echo " Your Shortlist Web Application is now LIVE at:"
echo "   http://${PUBLIC_IP}/"
echo ""
echo " Useful management commands:"
echo "   - View running logs:    docker compose logs -f"
echo "   - Check service status: docker compose ps"
echo "   - Restart application:  docker compose restart"
echo "   - Stop application:     docker compose down"
echo "======================================================================"
