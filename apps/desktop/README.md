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

## Signed and notarized build

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
