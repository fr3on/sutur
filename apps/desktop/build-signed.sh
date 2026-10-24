#!/usr/bin/env bash
# Build, sign and notarize the Sutur Mac app (Apple Silicon + Intel in one app).
#
# Needs these environment variables (set them in your shell, never in a file):
#   APPLE_SIGNING_IDENTITY  e.g. "Developer ID Application: Your Name (TEAMID)"   (see: security find-identity -v -p codesigning)
#   APPLE_ID                the Apple account email
#   APPLE_PASSWORD          an app-specific password from appleid.apple.com (not the account password)
#   APPLE_TEAM_ID           the 10-character Team ID from developer.apple.com > Membership
# Tauri signs with the hardened runtime and sends the app to Apple for notarization when all four are set.
set -euo pipefail
cd "$(dirname "$0")"

for v in APPLE_SIGNING_IDENTITY APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID; do
  [ -n "${!v:-}" ] || { echo "Missing $v (see the header of this script)." >&2; exit 1; }
done
security find-identity -v -p codesigning | grep -F "$APPLE_SIGNING_IDENTITY" >/dev/null \
  || { echo "No certificate named '$APPLE_SIGNING_IDENTITY' in the keychain. List them with: security find-identity -v -p codesigning" >&2; exit 1; }

rustup target add aarch64-apple-darwin x86_64-apple-darwin >/dev/null
npx tauri build --target universal-apple-darwin

B=src-tauri/target/universal-apple-darwin/release/bundle
APP="$B/macos/Sutur.app"; DMG=$(ls "$B"/dmg/*.dmg)
echo "--- checks"
codesign --verify --deep --strict --verbose=2 "$APP"
spctl -a -vv "$APP"                       # should say: accepted, source=Notarized Developer ID
xcrun stapler validate "$APP"             # the notarization ticket is attached to the app
lipo -archs "$APP/Contents/MacOS/sutur-app"
echo "--- done: $DMG"
