#!/bin/sh
# Install (or update) the community-mirror service on one official onion mirror. Run from the Mac; re-running is safe.
#   deploy/install-mirrord.sh                                  onion #1 (root@xcoin-onion)
#   XCOIN_ONION_HOST=root@<host> deploy/install-mirrord.sh      another official onion
# Installs mirrors/mirrord.py + checker/survival.py to /opt/xcoin-mirrors, a no-login user, the shared nginx config
# (adds /submit and /community.json), and two systemd units: the form (always on) and the hourly check (timer).
# Opens no port: the form listens on 127.0.0.1:8081 and only nginx (Tor) reaches it. Nothing secret is copied.
set -eu
HOST=${XCOIN_ONION_HOST:-root@xcoin-onion}
here=$(cd "$(dirname "$0")/.." && pwd)
COPYFILE_DISABLE=1 tar --no-xattrs -cf - -C "$here/mirrors" mirrord.py -C "$here/checker" survival.py \
    -C "$here/deploy" nginx-xcoin-survival.conf official-onions.txt \
  | ssh "$HOST" 'set -e; t=$(mktemp -d); tar -C "$t" -xf -
id xcoin-mirrors >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin xcoin-mirrors
install -d -m 755 /opt/xcoin-mirrors
install -m 644 "$t/mirrord.py" "$t/survival.py" /opt/xcoin-mirrors/
install -d -o xcoin-mirrors -g xcoin-mirrors -m 755 /var/lib/xcoin-mirrors
self=$(cat /var/lib/tor/xcoin-survival/hostname)
python3 - "$self" "$t/official-onions.txt" > /etc/xcoin-mirrors.json <<PY
import json, sys
print(json.dumps({"self": sys.argv[1], "official": [l.strip() for l in open(sys.argv[2]) if l.strip()]}, indent=1))
PY
chmod 644 /etc/xcoin-mirrors.json
grep -q "$self" "$t/official-onions.txt" || echo "WARNING: this server ($self) is not in official-onions.txt"
install -m 644 "$t/nginx-xcoin-survival.conf" /etc/nginx/sites-available/xcoin-survival
nginx -t 2>&1 | tail -1 && systemctl reload nginx
U=/etc/systemd/system
common="User=xcoin-mirrors
Group=xcoin-mirrors
Environment=XCOIN_CHECKER_DIR=/opt/xcoin-mirrors
Nice=10
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/xcoin-mirrors"
printf "[Unit]\nDescription=xCoin survival: community mirror submit form\nAfter=network.target\n\n[Service]\nExecStart=/usr/bin/python3 /opt/xcoin-mirrors/mirrord.py serve\nRestart=always\nMemoryMax=64M\nCPUQuota=10%%\n%s\n\n[Install]\nWantedBy=multi-user.target\n" "$common" > $U/xcoin-mirrors-web.service
printf "[Unit]\nDescription=xCoin survival: check community mirrors over Tor\nAfter=tor.service\n\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /opt/xcoin-mirrors/mirrord.py check\nMemoryMax=128M\nCPUQuota=15%%\nTimeoutStartSec=50min\n%s\n" "$common" > $U/xcoin-mirrors-check.service
printf "[Unit]\nDescription=Hourly community mirror check\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=1h\nRandomizedDelaySec=10min\n\n[Install]\nWantedBy=timers.target\n" > $U/xcoin-mirrors-check.timer
systemctl daemon-reload
systemctl enable --now xcoin-mirrors-web.service xcoin-mirrors-check.timer >/dev/null 2>&1
systemctl restart xcoin-mirrors-web.service
systemctl start --no-block xcoin-mirrors-check.service
sleep 2; rm -rf "$t"
echo "self: $self"
echo "form: $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/submit) (200 = ok), web service $(systemctl is-active xcoin-mirrors-web), timer $(systemctl is-active xcoin-mirrors-check.timer)"'
echo "installed on $HOST. The first check runs now (a few minutes); then /community.json appears."
