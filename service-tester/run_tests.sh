#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_TESTER_DIR="$SCRIPT_DIR/../build-tester"

HEADFUL=""
PROFILE_COUNT=6
PROXIES="$SCRIPT_DIR/proxies.txt"
EXECUTABLE_PATH=""
EXTRA_ARGS=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile-count)
            PROFILE_COUNT="$2"
            shift 2
            ;;
        --proxies)
            PROXIES="$2"
            shift 2
            ;;
        --headful)
            HEADFUL="--headful"
            shift
            ;;
        --no-cert)
            EXTRA_ARGS="$EXTRA_ARGS --no-cert"
            shift
            ;;
        --save-cert)
            EXTRA_ARGS="$EXTRA_ARGS --save-cert $2"
            shift 2
            ;;
        --executable-path)
            EXECUTABLE_PATH="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--profile-count N] [--proxies PATH] [--headful] [--no-cert] [--save-cert PATH] [--executable-path PATH]"
            exit 1
            ;;
    esac
done

echo "==> Profile count:   $PROFILE_COUNT"

# Install npm deps in build-tester (for esbuild — needed to build TypeScript bundle)
if [ ! -d "$BUILD_TESTER_DIR/node_modules" ]; then
    echo "==> Installing build-tester npm dependencies..."
    (cd "$BUILD_TESTER_DIR" && npm install --silent)
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"

echo "==> Building camoufox wheel from ../pythonlib..."
$PIP install -q build
rm -rf ../pythonlib/dist
(cd ../pythonlib && "$SCRIPT_DIR/.venv/bin/python" -m build --wheel -o dist >/dev/null)

echo "==> Installing camoufox from local wheel..."
$PIP uninstall -y camoufox cloverlabs-camoufox >/dev/null 2>&1 || true
$PIP install -q --force-reinstall ../pythonlib/dist/*.whl

# Resolve the binary to test against:
#  - explicit --executable-path wins
#  - otherwise auto-detect the locally compiled binary
#    macOS: Camoufox.app/Contents/MacOS/camoufox  (bare bin/camoufox-bin can't find dylibs)
#    Linux: bin/camoufox-bin
if [[ -z "$EXECUTABLE_PATH" ]]; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
        LOCAL_GLOB=(../camoufox-*/obj-*-apple-darwin/dist/Camoufox.app/Contents/MacOS/camoufox)
    else
        LOCAL_GLOB=(../camoufox-*/obj-*-linux-*/dist/bin/camoufox-bin)
    fi
    # shellcheck disable=SC2012
    EXECUTABLE_PATH=$(ls -1t "${LOCAL_GLOB[@]}" 2>/dev/null | head -1 || true)
    if [[ -z "$EXECUTABLE_PATH" || ! -f "$EXECUTABLE_PATH" ]]; then
        echo "ERROR: no local Camoufox build found at ${LOCAL_GLOB[0]}" >&2
        echo "  Build with 'make build' from the camoufox root, or pass --executable-path PATH." >&2
        exit 1
    fi
    EXECUTABLE_PATH=$(cd "$(dirname "$EXECUTABLE_PATH")" && pwd)/$(basename "$EXECUTABLE_PATH")
fi

# macOS .app: pythonlib reads properties.json from the executable's parent dir,
# but the bundle stores it in Contents/Resources/. Copy it into MacOS/ if missing.
if [[ "$(uname -s)" == "Darwin" && "$EXECUTABLE_PATH" == */Camoufox.app/Contents/MacOS/* ]]; then
    MACOS_DIR=$(dirname "$EXECUTABLE_PATH")
    RESOURCES_PROPS="${MACOS_DIR%/MacOS}/Resources/properties.json"
    if [[ ! -f "$MACOS_DIR/properties.json" && -f "$RESOURCES_PROPS" ]]; then
        cp "$RESOURCES_PROPS" "$MACOS_DIR/properties.json"
        echo "==> Copied properties.json into $MACOS_DIR/"
    fi
fi

echo
echo "════════════════════════════════════════════════════════════"
echo "  Running service tests against: $EXECUTABLE_PATH"
echo "════════════════════════════════════════════════════════════"
exec $PYTHON run_tests.py \
    --executable-path "$EXECUTABLE_PATH" \
    --profile-count "$PROFILE_COUNT" \
    --proxies "$PROXIES" \
    $HEADFUL \
    $EXTRA_ARGS
