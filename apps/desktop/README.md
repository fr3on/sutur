# Sutur for desktop

A small [Tauri](https://tauri.app) window for Mac, Windows and Linux around [sutur.ink/app](https://sutur.ink/app): the reading app in its own window, with a menu (Home, Library, Reading now, Downloads), back and forward, zoom, and a title bar that drags the window. It holds no book data and no accounts of its own; you sign in on the site.

## Download

On the [Releases](https://github.com/fr3on/sutur/releases) page:

| Platform | File | Notes |
|---|---|---|
| Mac | `Sutur.dmg` | Apple Silicon and Intel, signed and notarized by Apple |
| Windows 10 or later, 64-bit | `Sutur-setup.exe` | one user, no administrator rights; **not code-signed yet**, so Windows SmartScreen may warn |
| Linux, 64-bit | `Sutur.AppImage`, `Sutur.deb` | the .deb needs WebKitGTK |

The window title bar is native on Windows and Linux; the Mac keeps its overlay title bar.

## Build it yourself

You need Rust, Node and Xcode command line tools.

```bash
cd apps/desktop
npm install
npx tauri build            # unsigned, for this Mac only
```

## Release build in GitHub Actions

[`.github/workflows/desktop.yml`](../../.github/workflows/desktop.yml) creates one release and builds each platform on its own runner (Mac signed and notarized, Windows installer, Linux AppImage and .deb). Run it from the Actions tab (give a version such as `0.1.0` and, if you like, only some platforms such as `windows,linux`) or push a tag like `desktop-v0.1.0`.

The Mac job needs these secrets (Windows and Linux need none). Add them under Settings > Secrets and variables > Actions (never in a file or a chat):

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
