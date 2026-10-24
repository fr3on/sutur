# Sutur for Mac

A small [Tauri](https://tauri.app) window around [sutur.ink/app](https://sutur.ink/app): the reading app in its own window, with a menu (Home, Library, Reading now, Downloads), back and forward, zoom, and a title bar that drags the window. It holds no book data and no accounts of its own; you sign in on the site.

## Download

Signed and notarized builds are on the [Releases](https://github.com/fr3on/sutur/releases) page (`Sutur.dmg`, Apple Silicon and Intel).

## Build it yourself

You need Rust, Node and Xcode command line tools.

```bash
cd apps/desktop
npm install
npx tauri build            # unsigned, for this Mac only
```

## Release build in GitHub Actions

[`.github/workflows/desktop.yml`](../../.github/workflows/desktop.yml) builds, signs and notarizes the app on a Mac runner and publishes `Sutur.dmg` to a release. Run it from the Actions tab (give a version such as `0.1.0`) or push a tag like `desktop-v0.1.0`.

Add these under Settings > Secrets and variables > Actions (never in a file or a chat):

| Secret | What |
|---|---|
| `APPLE_CERTIFICATE` | the Developer ID Application certificate exported as a `.p12`, base64 encoded: `base64 -i cert.p12 \| pbcopy` |
| `APPLE_CERTIFICATE_PASSWORD` | the password you chose when exporting the `.p12` |
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | the Apple account email |
| `APPLE_PASSWORD` | an app-specific password from appleid.apple.com |
| `APPLE_TEAM_ID` | the 10-character Team ID |

The job stops at the start and names any secret that is missing. The download link is `https://github.com/fr3on/sutur/releases/latest/download/Sutur.dmg`.

## Signed and notarized build on your own Mac

Set these in your shell (never in a file). They come from your Apple Developer account:

| Variable | What |
|---|---|
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | the Apple account email |
| `APPLE_PASSWORD` | an app-specific password from appleid.apple.com |
| `APPLE_TEAM_ID` | the 10-character Team ID |

```bash
./build-signed.sh
```

It builds one app for Apple Silicon and Intel, signs it, sends it to Apple for notarization, and checks the result (`spctl` should report "Notarized Developer ID").

The bundle identifier is `ink.sutur.desktop`. `ink.sutur.app` is kept for the iPhone app.
