# Patch Dependencies

Every patch and its dependencies. A patch must be applied **after** its dependencies.

## Foundation (no dependencies)

| Patch | Description |
|-------|-------------|
| `browser-init.patch` | Initializes MaskConfig system |
| `chromeutil.patch` | Adds MaskConfig to ChromeUtils API |
| `config.patch` | Wires up lw/moz.build for settings |
| `playwright/0-playwright.patch` | Playwright/Juggler automation protocol |
| `playwright/1-leak-fixes.patch` | Depends on `0-playwright.patch` |

## MaskConfig-dependent (require browser-init + chromeutil)

| Patch | Additional Dependencies | Shared Files |
|-------|------------------------|--------------|
| `fingerprint-injection.patch` | - | dom/base/nsGlobalWindowInner.cpp, moz.build |
| `navigator-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build, Window.webidl |
| `network-patches.patch` | - | netwerk/protocol/http/nsHttpHandler.cpp |
| `anti-font-fingerprinting.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build |
| `audio-context-spoofing.patch` | - | dom/media/webaudio/ |
| `audio-fingerprint-manager.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build |
| `canvas-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build |
| `disable-remote-subframes.patch` | - | docshell/base/BrowsingContext.cpp |
| `font-hijacker.patch` | - | gfx/thebes/ |
| `font-list-spoofing.patch` | `fingerprint-injection.patch`, `font-hijacker.patch` | nsGlobalWindowInner, gfxPlatformFontList.cpp |
| `geolocation-spoofing.patch` | - | dom/geolocation/ |
| `global-style-sheets.patch` | - | layout/style/ |
| `locale-spoofing.patch` | `browser-init.patch` | browser-init.js |
| `media-device-spoofing.patch` | - | dom/media/ |
| `screen-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build, Window.webidl |
| `speech-voices-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build |
| `timezone-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, DateTime.h/cpp |
| `voice-spoofing.patch` | `speech-voices-spoofing.patch` | dom/media/webspeech/synth/moz.build |
| `webgl-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build, Window.webidl |
| `webrtc-ip-spoofing.patch` | `fingerprint-injection.patch` | nsGlobalWindowInner.cpp/h, moz.build |

## Independent patches (no MaskConfig, no shared files)

| Patch | Notes |
|-------|-------|
| `all-addons-private-mode.patch` | Standalone |
| `cross-process-storage.patch` | Shares ContentParent.cpp with `macos-sandbox-crash-fix.patch` |
| `disable-extension-newtab.patch` | Standalone |
| `force-default-pointer.patch` | Standalone |
| `macos-sandbox-crash-fix.patch` | Shares ContentParent.cpp with `cross-process-storage.patch` |
| `no-css-animations.patch` | Standalone |
| `no-search-engines.patch` | Shares UrlbarProviderInterventions with librewolf urlbarprovider |
| `pin-addons.patch` | Standalone |
| `shadow-root-bypass.patch` | Standalone |
| `windows-theming-bug-modified.patch` | Standalone |

## LibreWolf patches

| Patch | Dependencies |
|-------|-------------|
| `librewolf/bootstrap.patch` | Standalone |
| `librewolf/custom-ubo-assets-bootstrap-location.patch` | Standalone |
| `librewolf/dbus_name.patch` | Standalone |
| `librewolf/devtools-bypass.patch` | Standalone |
| `librewolf/disable-data-reporting-at-compile-time.patch` | Standalone |
| `librewolf/mozilla_dirs.patch` | Standalone |
| `librewolf/rust-gentoo-musl.patch` | Standalone |
| `librewolf/sed-patches/stop-undesired-requests.patch` | Standalone |
| `librewolf/urlbarprovider-interventions.patch` | Standalone |
| `librewolf/ui-patches/firefox-view.patch` | Standalone |
| `librewolf/ui-patches/handlers.patch` | Standalone |
| `librewolf/ui-patches/hide-default-browser.patch` | Standalone |
| `librewolf/ui-patches/remove-cfrprefs.patch` | Standalone |
| `librewolf/ui-patches/remove-organization-policy-banner.patch` | Standalone |

## Ghostery patches

| Patch | Dependencies |
|-------|-------------|
| `ghostery/Disable-Onboarding-Messages.patch` | Standalone |

## Shared file hotspots

Files modified by many patches (high conflict risk):

- **`dom/base/nsGlobalWindowInner.cpp`** — 10 patches (fingerprint-injection + all manager patches)
- **`dom/base/nsGlobalWindowInner.h`** — 9 patches
- **`dom/base/moz.build`** — 11 patches
- **`dom/webidl/Window.webidl`** — 9 patches
