#!/usr/bin/env bash
# provision.sh — bring a fresh Ubuntu 24.04 box to a state where
# `docker compose up -d` will work for openclaw-config.
#
# Idempotent: safe to re-run. Does not touch .env or any application config.
#
# Usage:  sudo ./scripts/provision.sh

set -euo pipefail

# --- preflight --------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "Re-run with sudo: sudo $0" >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-}"
if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
  echo "Run as a normal user via sudo (not as root directly):" >&2
  echo "  sudo $0" >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
  echo "Warning: tested on Ubuntu 24.04 LTS, detected ${PRETTY_NAME:-unknown}." >&2
  read -rp "Continue anyway? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# --- 1. base packages -------------------------------------------------------
echo ">>> Updating apt and installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates curl gnupg git jq ufw unattended-upgrades

# --- 2. Docker engine + compose plugin --------------------------------------
if ! command -v docker >/dev/null; then
  echo ">>> Installing Docker engine + compose plugin"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
else
  echo ">>> Docker already installed, skipping"
fi

# --- 3. docker group membership for the invoking user -----------------------
GROUP_CHANGED=0
if ! id -nG "$TARGET_USER" | grep -qw docker; then
  echo ">>> Adding $TARGET_USER to the docker group"
  usermod -aG docker "$TARGET_USER"
  GROUP_CHANGED=1
fi

# --- 4. enable + start docker -----------------------------------------------
systemctl enable --now docker

# --- 5. host firewall -------------------------------------------------------
# Default-deny inbound. Tailscale handles its own encrypted overlay; nothing
# from this stack needs to be reachable on the public interface.
echo ">>> Configuring ufw (default deny inbound, allow outbound)"
ufw --force default deny incoming  >/dev/null
ufw --force default allow outgoing >/dev/null
ufw --force enable                 >/dev/null

# --- 6. unattended security upgrades ----------------------------------------
echo ">>> Enabling unattended security upgrades"
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null

# --- done -------------------------------------------------------------------
cat <<EOF

===========================================================================
Provisioning complete.

Next steps:
  1. cp .env.example .env   &&   edit .env with your credentials
     (see docs/SETUP.md for where each value comes from)
  2. docker compose up -d --build
  3. Watch:  docker compose logs -f openclaw

EOF

if [[ "$GROUP_CHANGED" == "1" ]]; then
  cat <<EOF
NOTE: '$TARGET_USER' was just added to the 'docker' group. Log out and back
in (or run 'newgrp docker') before running 'docker compose up' as that user.

EOF
fi
