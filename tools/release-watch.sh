#!/bin/sh
# Daily (launchd): is there an xCoin node release the survival page does not show yet? Changes nothing; only tells you.
#   install once:  tools/release-watch.sh --install      remove:  tools/release-watch.sh --uninstall
here=$(cd "$(dirname "$0")/.." && pwd)
PL="$HOME/Library/LaunchAgents/com.xcoin.survival-release-watch.plist"
case "${1:-}" in
  --install)
    sed "s#__HERE__#$here#g" "$here/tools/launchd/com.xcoin.survival-release-watch.plist" > "$PL"
    launchctl bootout "gui/$(id -u)" "$PL" 2>/dev/null; launchctl bootstrap "gui/$(id -u)" "$PL" && echo "installed: checks daily at 10:00 (and now)"
    exit ;;
  --uninstall) launchctl bootout "gui/$(id -u)" "$PL" 2>/dev/null; rm -f "$PL"; echo removed; exit ;;
esac
out=$(python3 "$here/tools/set-release.py" --check 2>&1); rc=$?
echo "$(date -u +%FT%TZ) $out" >> "$HOME/Library/Logs/xcoin-survival-release-watch.log"
if [ $rc = 1 ]; then
  osascript -e "display notification \"$(echo "$out" | sed 's/"//g')\" with title \"xCoin survival page is out of date\" sound name \"Glass\""
fi
