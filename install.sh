#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "${EUID}" -ne 0 ]; then
  echo "Start met: sudo bash install.sh" >&2; exit 1
fi
. /etc/os-release
case "${ID}:${VERSION_ID}" in
  ubuntu:22.04|ubuntu:24.04|ubuntu:26.04) ;;
  *) echo "De begeleide installatie ondersteunt Ubuntu 22.04, 24.04 en 26.04 LTS." >&2; exit 1 ;;
esac
# Validate deployment manifest before modifying system packages.
"$ROOT/bin/openvoorouders" controleer-manifest "${OVO_MANIFEST:-$ROOT/releases/stable.json}"
if ! command -v docker >/dev/null 2>&1; then
  for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      echo "Conflicterend pakket: $package. We verwijderen bestaande software niet automatisch." >&2; exit 1
    fi
  done
  echo "Docker Engine wordt geïnstalleerd via de officiële Docker-APT-repository."
  apt-get update
  apt-get install -y ca-certificates curl python3
  install -m 0755 -d /etc/apt/keyrings
  curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
if [ -f /opt/openvoorouders/current.json ]; then
  /opt/openvoorouders/host/bin/openvoorouders installatie-afronden
else
read -r -p "Lokaal IP-adres van deze Linux-machine (127.0.0.1 voor alleen deze pc): " bind
read -r -p "Poort [8080]: " port
port="${port:-8080}"
read -r -p "Webadres voor je browser [http://${bind}:${port}]: " address
address="${address:-http://${bind}:${port}}"
"$ROOT/bin/openvoorouders" installeren "${OVO_MANIFEST:-$ROOT/releases/stable.json}" --bind "$bind" --poort "$port" --adres "$address"
fi
ln -sfn /opt/openvoorouders/host/bin/openvoorouders /usr/local/bin/openvoorouders
cat > /etc/systemd/system/openvoorouders-backup.service <<'EOF'
[Unit]
Description=Openvoorouders dagelijkse back-up
[Service]
Type=oneshot
ExecStart=/usr/local/bin/openvoorouders backup
UMask=0077
Restart=on-failure
RestartSec=30m
EOF
cat > /etc/systemd/system/openvoorouders-backup.timer <<'EOF'
[Unit]
Description=Openvoorouders dagelijkse back-up
[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
RandomizedDelaySec=15m
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now openvoorouders-backup.timer
cat > /etc/systemd/system/openvoorouders-versiecontrole.service <<'EOF'
[Unit]
Description=Openvoorouders stabiele releases controleren
[Service]
Type=oneshot
ExecStart=/usr/local/bin/openvoorouders versiecontrole
UMask=0077
EOF
cat > /etc/systemd/system/openvoorouders-versiecontrole.timer <<'EOF'
[Unit]
Description=Openvoorouders dagelijkse versiecontrole
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
RandomizedDelaySec=15m
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now openvoorouders-versiecontrole.timer
