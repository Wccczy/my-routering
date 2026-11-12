#!/bin/sh
# Install as /etc/openclash/custom/openclash_custom_overwrite.sh on the small router only.
# Merge existing device-specific hooks before installing; this file sets no IP, MTU or provider names.
CONFIG_FILE="$1"
POLICY_DIR="/etc/openclash/custom"
TEMPLATE="$POLICY_DIR/my-routering-small.ini"

if [ -z "$CONFIG_FILE" ] || [ ! -f "$CONFIG_FILE" ]; then
   echo "Error: missing OpenClash candidate configuration" >&2
   exit 1
fi

if ruby "$POLICY_DIR/openclash_policy.rb" apply-small "$CONFIG_FILE" "$TEMPLATE"; then
   logger -t openclash "Small policy applied: MMDB, memconservative, strict AI, empty-pool REJECT, process-match off"
else
   logger -t openclash "Small policy failed: refuse unprotected or oversized candidate"
   # OpenClash may ignore the hook exit code; do not leave a failed candidate loadable.
   mv "$CONFIG_FILE" "$CONFIG_FILE.policy-rejected"
   exit 1
fi

# Run audit-small explicitly after startup on constrained devices.
# Avoid an extra Ruby/API snapshot process during the core's peak allocation window.
exit 0
