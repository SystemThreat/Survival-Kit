#!/bin/bash
# setup-onion.sh: turn a fresh Ubuntu 24.04 server into an xCoin survival-sheet onion mirror. Run as root, once.
# Re-running is safe: every step checks before it changes anything.
#
#   The server opens NO port to the internet. Tor makes outgoing connections only; nginx answers on 127.0.0.1:8080
#   for Tor alone. SSH is Tailscale only. The onion address comes from a key file that is copied in separately
#   (restore-onion-key.sh), never generated here, so the address is the founder's chosen xcoin… one.
#
#   What it installs: tor (from the Tor Project's own repository, signing key checked by fingerprint), nginx-light,
#   unattended-upgrades, ufw. What it serves: /var/www/xcoin-survival (index.html, manifest.json, manifest.json.sig,
#   allowed_signers), copied in by publish.sh.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
. /etc/os-release; [ "$VERSION_CODENAME" = noble ] || { echo "expected Ubuntu 24.04 (noble), found $VERSION_CODENAME"; exit 1; }

TOR_FPR=A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89     # the Tor Project's archive signing key (deb.torproject.org)
WEB=/var/www/xcoin-survival

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q apt-transport-https gnupg curl nginx-light ufw unattended-upgrades

echo "== Tor from the Tor Project"
if [ ! -f /usr/share/keyrings/tor-archive-keyring.gpg ]; then
  curl -fsSL https://deb.torproject.org/torproject.org/$TOR_FPR.asc | gpg --dearmor > /tmp/tor.gpg
  got=$(gpg --show-keys --with-colons /tmp/tor.gpg | awk -F: '$1=="fpr"{print $10; exit}')
  [ "$got" = "$TOR_FPR" ] || { echo "Tor signing key fingerprint mismatch: $got"; rm -f /tmp/tor.gpg; exit 1; }
  install -m 644 /tmp/tor.gpg /usr/share/keyrings/tor-archive-keyring.gpg; rm -f /tmp/tor.gpg
fi
echo "deb [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org noble main" \
  > /etc/apt/sources.list.d/tor.list
apt-get update -q
apt-get install -y -q tor deb.torproject.org-keyring

echo "== nginx: 127.0.0.1:8080 only, no version, no logs of visitors"
install -d -m 755 "$WEB"
cat > /etc/nginx/sites-available/xcoin-survival <<'NGINX'
server {
    listen 127.0.0.1:8080 default_server;
    server_name _;
    root /var/www/xcoin-survival;
    index index.html;
    access_log off;                       # an onion mirror keeps no record of who read it
    server_tokens off;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
    location / { try_files $uri =404; }
}
NGINX
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/xcoin-survival /etc/nginx/sites-enabled/xcoin-survival
sed -i 's/^\s*#\?\s*server_tokens.*/\tserver_tokens off;/' /etc/nginx/nginx.conf
nginx -t && systemctl enable --now nginx && systemctl reload nginx

echo "== Tor onion service (key restored separately)"
install -d -o debian-tor -g debian-tor -m 700 /var/lib/tor/xcoin-survival
grep -q '^HiddenServiceDir /var/lib/tor/xcoin-survival' /etc/tor/torrc || cat >> /etc/tor/torrc <<'TORRC'

# xCoin survival sheet mirror
HiddenServiceDir /var/lib/tor/xcoin-survival/
HiddenServicePort 80 127.0.0.1:8080
TORRC
systemctl enable tor

echo "== firewall: nothing in except Tailscale"
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0
ufw --force enable

echo "== automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT

echo
echo "done. Next, from the Mac: restore-onion-key.sh (the address), then publish.sh (the signed page)."
echo "Tor starts serving once the key is in place: systemctl restart tor"
