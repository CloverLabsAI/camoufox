# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Camoufox?

Camoufox is a stealthy, anti-detect custom build of Firefox for web scraping and bot evasion. It consists of two layers: C++ patches applied to Firefox source code (fingerprint spoofing, stealth, debloating) and a Python wrapper library around Playwright for automation.

Current base: Firefox v146 (`upstream.sh` defines version/release).

## Build Commands

```bash
# Full build pipeline
make fetch              # Download Firefox source tarball
make setup              # Extract source + init git repo for development
make bootstrap          # Install system deps + mach bootstrap (runs make dir)
make build              # Build Firefox (runs make dir if needed)

# Platform packaging
make package-linux arch=x86_64
make package-macos arch=arm64
make package-windows arch=x86_64

# Development
make edits              # Interactive developer UI for patch management
make run                # Run built browser with debug mode
make ff-dbg             # Build vanilla Firefox with minimal patches (debugging)

# Patch management
make patch ./patches/foo.patch     # Apply a single patch
make unpatch ./patches/foo.patch   # Reverse a single patch
make workspace ./patches/foo.patch # Set workspace to edit a patch
make diff                          # Show diff since first checkpoint
```

## Testing

**Both test suites are required for PRs.** They test different layers.

### build-tester (browser binary layer)
```bash
cd build-tester
npm install
pip install -r requirements.txt
python scripts/run_tests.py /path/to/camoufox-binary
```
Tests raw binary with manual fingerprint injection. 8 profiles (6 per-context + 2 global). No proxies needed. Validates injected values match page output.

### service_tests (Python package layer)
```bash
cd service_tests
cp proxies.txt.example proxies.txt  # one proxy per line: user:pass@domain:port
./run_tests.sh
```
Tests full stack via `AsyncNewContext` API. 6 per-context profiles. Requires real proxies. Failures indicate Python package bugs, not browser bugs.

### Playwright tests
```bash
make tests                       # headless
make tests headful=true          # headful
```

## Architecture

### Browser patches (`patches/`)
~40 patch files applied to Firefox source via `scripts/patch.py`. Categories:
- **Fingerprint spoofing**: navigator, screen, WebGL, canvas, audio, fonts, WebRTC, geolocation, battery
- **Stealth**: hide automation (Juggler protocol patches), remove `navigator.webdriver`, fix headless detection
- **Debloating**: remove Mozilla services, telemetry, unnecessary features
- **Infrastructure**: `browser-init.patch` and `chromeutil.patch` are foundational — they set up the config system

### Custom browser code (`additions/`)
- `additions/camoucfg/`: C++ config reader (parses `CAMOU_CONFIG` env var and `camoucfg.jvv`)
- `additions/browser/`: Custom browser chrome JS
- `additions/juggler/`: Patched Juggler automation protocol (how Playwright talks to Camoufox)

### Browser settings (`settings/`)
- `camoufox.cfg`: Firefox prefs (debloating, privacy, performance)
- `camoucfg.jvv`: Fingerprint spoofing config format
- `properties.json`: Browser property definitions
- `chrome.css`: Minimal UI theme

### Python library (`pythonlib/camoufox/`)
Poetry-managed package (Python ^3.10). Key modules:
- `sync_api.py` / `async_api.py`: Main entry points (`Camoufox` / `AsyncCamoufox` context managers)
- `fingerprints.py`: Fingerprint generation via BrowserForge with OS-consistent fonts/WebGL
- `pkgman.py`: Browser binary download/version management
- `multiversion.py`: Multiple Camoufox version/channel support
- `ip.py` / `geolocation.py`: Proxy IP detection and GeoIP integration
- `addons.py`: Firefox addon management (uBlock Origin, BPC)
- `server.py`: Remote Playwright server mode

### Build system (`scripts/`)
- `patch.py`: Applies all patches and generates mozconfig
- `package.py`: Creates platform-specific distributable packages
- `developer.py`: Interactive TUI for editing/managing patches
- `multibuild.py`: Orchestrates multi-target builds

### Bundled resources (`bundle/`)
System fonts for Windows, macOS, and Linux used in anti-font-fingerprinting.

## Development Workflow

**For browser/patch changes:**
1. `make edits` → click "Reset workspace"
2. Make changes in `camoufox-*/` source directory
3. `make build` → `make run` to test
4. In developer UI, click "Write workspace to patch" to save changes back to patch file
5. Run `build-tester` to validate

**For Python package changes:**
1. Edit files in `pythonlib/camoufox/`
2. Run `service_tests` with real proxies

## Key Details

- The Firefox source directory is `camoufox-{version}-{release}` (e.g., `camoufox-146.0.1-beta.25`), created by `make setup`
- Patches are applied in order by `scripts/patch.py` — order matters
- `CAMOU_CONFIG` env var is the primary way to pass fingerprint config to the browser at runtime
- Juggler is Firefox's equivalent of CDP (Chrome DevTools Protocol) — Camoufox patches it to hide automation signals
- CI builds via GitHub Actions matrix across Linux/macOS/Windows × x86_64/arm64/i686
