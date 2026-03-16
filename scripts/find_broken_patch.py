#!/usr/bin/env python3

"""
Binary search for the patch that leaks automation signals.

Builds Camoufox with progressively narrower subsets of patches,
testing each build against user-defined criteria until the
offending patch is isolated.

Prerequisites:
    - Firefox source already fetched and set up (make fetch && make setup)
    - Build dependencies installed (make bootstrap)

Usage:
    python3 scripts/find_broken_patch.py --target macos --arch arm64
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from _mixin import find_src_dir, get_moz_target, list_patches, run, temp_cd


# ---------------------------------------------------------------------------
# USER-DEFINED TEST CRITERIA — edit this function
# ---------------------------------------------------------------------------

def load_proxy():
    """Load proxy from .env file. Expects PROXY=user:pass@host:port"""
    from dotenv import load_dotenv

    load_dotenv()
    proxy_str = os.environ.get("PROXY")
    if not proxy_str:
        return None

    # Parse user:pass@host:port
    if "@" in proxy_str:
        creds, server = proxy_str.rsplit("@", 1)
        user, password = creds.split(":", 1)
        return {"server": f"http://{server}", "username": user, "password": password}
    return {"server": f"http://{proxy_str}"}


def test_criteria(app_path: str) -> bool:
    """
    Opens the test page, waits 15 seconds, then checks for a leak indicator.
    Returns True (pass) if no leak detected, False (fail) if leak detected.
    A leak is indicated by the presence of "body > p > a" or the text "scraping".
    """
    import time

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonlib"))
    from camoufox.sync_api import Camoufox

    binary = os.path.join(app_path, "Contents", "MacOS", "camoufox")
    proxy = load_proxy()
    if proxy:
        print(f"  Using proxy: {proxy['server']}")

    with Camoufox(executable_path=binary, headless=False, proxy=proxy, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.goto("https://bounty-nodejs.datashield.co/")
        time.sleep(15)

        # Check for pass indicators
        has_link = page.query_selector("body > p > a") is not None
        has_scraping = "scraping" in (page.content() or "").lower()
        passed = has_link or has_scraping

        if passed:
            print("  PASS: found 'body > p > a' or 'scraping' on page")
        else:
            print("  FAIL: page did not show expected content (bot detected)")

        page.close()
    return passed


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AVAILABLE_TARGETS = ["macos"]
AVAILABLE_ARCHS = ["x86_64", "arm64"]
BISECT_EXTRACT_DIR = "_bisect_extract"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def extract_zip(zip_path, dest_dir):
    """Extract a zip file and ensure binaries are executable."""
    import stat

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # 7z-created zips don't store Unix permissions, so fix up executables
    for root, _dirs, files in os.walk(dest_dir):
        for f in files:
            fp = os.path.join(root, f)
            # Mark binaries and scripts as executable
            if f in ("camoufox", "camoufox-bin", "firefox", "plugin-container") or f.endswith(".sh"):
                os.chmod(fp, os.stat(fp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def parse_upstream():
    """Read version and release from upstream.sh."""
    vals = {}
    with open("upstream.sh") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                vals[key.strip()] = value.strip()
    return vals["version"], vals["release"]


BASELINE_PATCHES = {
    "0-playwright.patch",
    "1-leak-fixes.patch",
    "anti-font-fingerprinting.patch",
    "audio-fingerprint-manager.patch",
    "browser-init.patch",
    "canvas-spoofing.patch",
    "chromeutil.patch",
    "config.patch",
    "fingerprint-injection.patch",
    "font-list-spoofing.patch",
    "navigator-spoofing.patch",
    "network-patches.patch",
}


def categorize_patches():
    """Split patches into baseline (always applied) and searchable patches.

    Baseline includes playwright patches and foundation patches
    (browser-init, chromeutil) needed for a functional browser.

    Returns (baseline_patches, search_patches) where search_patches
    are ordered non-roverfox first, then roverfox.
    """
    all_patches = list_patches(root_dir="patches")
    baseline = []
    non_baseline = []

    for p in all_patches:
        parts = os.path.normpath(p).split(os.sep)
        basename = os.path.basename(p)
        if "playwright" in parts or basename in BASELINE_PATCHES:
            baseline.append(p)
        else:
            non_baseline.append(p)

    # Order search patches: non-roverfox first, then roverfox
    non_roverfox = []
    roverfox = []
    for p in non_baseline:
        parts = os.path.normpath(p).split(os.sep)
        if "roverfox" in parts:
            roverfox.append(p)
        else:
            non_roverfox.append(p)

    return baseline, non_roverfox + roverfox


def write_mozconfig(target, arch):
    """Create mozconfig with the correct build target."""
    moz_target = get_moz_target(target, arch)
    shutil.copy("../assets/base.mozconfig", "mozconfig")

    with open("mozconfig", "a") as f:
        f.write(f"\nac_add_options --target={moz_target}\n")
        target_extra = os.path.join("..", "assets", f"{target}.mozconfig")
        if os.path.exists(target_extra):
            with open(target_extra) as tf:
                f.write(tf.read())


def reset_source(version, release):
    """Reset the source tree to unpatched state and re-copy additions."""
    run("git clean -fdx && git reset --hard unpatched", exit_on_fail=True)
    run(f"bash ../scripts/copy-additions.sh {version} {release}", exit_on_fail=True)


def apply_patches(patches):
    """Apply a list of patch files. Returns True on success."""
    for p in patches:
        # Patches are relative to repo root (e.g. patches/foo.patch).
        # Inside the source dir we need ../patches/foo.patch.
        patch_path = os.path.join("..", p)
        ret = os.system(f"patch -p1 --forward -l --binary -i {patch_path}")
        if ret != 0:
            print(f"WARNING: patch failed to apply cleanly: {p}")
            return False
    return True


def mark_result(label, arch, passed):
    """Rename the saved zip in dist/ to include pass/fail."""
    src = f"dist/{label}-mac.{arch}.zip"
    result = "pass" if passed else "fail"
    dst = f"dist/{label}-{result}-mac.{arch}.zip"
    if os.path.exists(src):
        os.rename(src, dst)
        print(f"  Saved: {dst}")


def build():
    """Run the build. Returns True on success."""
    ret = os.system("./mach build")
    return ret == 0


def package_and_extract(version, release, arch, label=None):
    """Package the build and extract to _bisect_extract/.

    If label is provided (e.g. "round-1"), the zip is saved to
    dist/ with the label and pass/fail result after testing.

    Returns the absolute path to the extracted Camoufox.app.
    """
    # Run package.py from repo root
    package_cmd = (
        f"python3 scripts/package.py macos"
        f" --includes settings/chrome.css settings/camoucfg.jvv settings/properties.json"
        f" --version {version} --release {release} --arch {arch}"
        f" --fonts windows linux"
    )
    ret = os.system(package_cmd)
    if ret != 0:
        print("ERROR: Packaging failed.")
        sys.exit(1)

    # Find the output zip
    zip_name = f"camoufox-{version}-{release}-mac.{arch}.zip"
    if not os.path.exists(zip_name):
        print(f"ERROR: Expected package not found: {zip_name}")
        sys.exit(1)

    # Save a copy if labelled
    if label:
        os.makedirs("dist", exist_ok=True)
        shutil.copy2(zip_name, f"dist/{label}-mac.{arch}.zip")

    # Clear and recreate extract directory
    if os.path.exists(BISECT_EXTRACT_DIR):
        shutil.rmtree(BISECT_EXTRACT_DIR)
    os.makedirs(BISECT_EXTRACT_DIR)

    # Extract
    extract_zip(zip_name, BISECT_EXTRACT_DIR)

    # Clean up original zip
    os.remove(zip_name)

    app_path = os.path.join(os.path.abspath(BISECT_EXTRACT_DIR), "Camoufox.app")
    if not os.path.exists(app_path):
        print(f"ERROR: Camoufox.app not found in extracted package at {app_path}")
        # List what was extracted for debugging
        print("Contents of extract dir:")
        for item in os.listdir(BISECT_EXTRACT_DIR):
            print(f"  {item}")
        sys.exit(1)

    return app_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Binary search for the patch that leaks automation signals."
    )
    parser.add_argument(
        "--target",
        choices=AVAILABLE_TARGETS,
        default="macos",
        help="Build target platform (default: macos)",
    )
    parser.add_argument(
        "--arch",
        choices=AVAILABLE_ARCHS,
        required=True,
        help="Build architecture",
    )
    parser.add_argument(
        "--test-only",
        metavar="ZIP",
        help="Skip building. Extract the given zip from dist/ and run test_criteria only.",
    )
    args = parser.parse_args()

    # Quick sanity-check mode: extract an existing zip and test it
    if args.test_only:
        zip_path = args.test_only
        if not os.path.exists(zip_path):
            print(f"ERROR: {zip_path} not found.")
            sys.exit(1)
        print(f"Extracting {zip_path} ...")
        if os.path.exists(BISECT_EXTRACT_DIR):
            shutil.rmtree(BISECT_EXTRACT_DIR)
        os.makedirs(BISECT_EXTRACT_DIR)
        extract_zip(zip_path, BISECT_EXTRACT_DIR)
        app_path = os.path.join(os.path.abspath(BISECT_EXTRACT_DIR), "Camoufox.app")
        if not os.path.exists(app_path):
            print(f"ERROR: Camoufox.app not found in {BISECT_EXTRACT_DIR}/")
            sys.exit(1)
        print(f"Running test_criteria against: {app_path}")
        passed = test_criteria(app_path)
        print("PASS" if passed else "FAIL")
        sys.exit(0 if passed else 1)

    os.environ["BUILD_TARGET"] = f"{args.target},{args.arch}"

    version, release = parse_upstream()
    src_dir = find_src_dir(".", version, release)
    abs_src_dir = os.path.abspath(src_dir)

    baseline_patches, search_patches = categorize_patches()

    total = len(search_patches)
    iterations = math.ceil(math.log2(total)) if total > 1 else 1

    print(f"Baseline patches (always applied):")
    for p in baseline_patches:
        print(f"  {p}")

    print(f"\nSearch patches ({total} total, ~{iterations} iterations):")
    for i, p in enumerate(search_patches):
        print(f"  [{i:>2}] {p}")
    print()

    # ------------------------------------------------------------------
    # Step 0: Build with ONLY baseline patches as sanity check.
    # If this fails, the test criteria or playwbaselineright patches are broken.
    # ------------------------------------------------------------------
    print("=" * 70)
    print("Step 0: Building with ONLY baseline patches (sanity check)")
    print("=" * 70)

    with temp_cd(abs_src_dir):
        reset_source(version, release)
        write_mozconfig(args.target, args.arch)

        if not apply_patches(baseline_patches):
            print("ERROR: baseline patches failed to apply.")
            sys.exit(1)

        # Signal that patching is done
        open("_READY", "w").close()

        if not build():
            print("ERROR: baseline-only build failed.")
            sys.exit(1)

    # Package and extract
    app_path = package_and_extract(version, release, args.arch, label="round-0-sanity")
    print(f"\nRunning test criteria against baseline-only build: {app_path}")
    passed = test_criteria(app_path)
    mark_result("round-0-sanity", args.arch, passed)

    if not passed:
        print("FAIL — test criteria failed on baseline-only build.")
        print("This means the test criteria or baseline patches are broken.")
        sys.exit(1)

    print("PASS — baseline-only build passes. Proceeding with binary search.\n")

    # ------------------------------------------------------------------
    # Binary search
    # ------------------------------------------------------------------
    lo, hi = 0, total - 1
    iteration = 0

    while lo < hi:
        iteration += 1
        mid = (lo + hi) // 2

        print("=" * 70)
        print(f"Iteration {iteration}: testing patches [0..{mid}] (range [{lo}..{hi}])")
        print(f"Applying playwright + {mid + 1}/{total} search patches")
        print("=" * 70)

        with temp_cd(abs_src_dir):
            reset_source(version, release)
            write_mozconfig(args.target, args.arch)

            all_to_apply = baseline_patches + search_patches[: mid + 1]
            if not apply_patches(all_to_apply):
                print("ERROR: Patches failed to apply. Cannot continue binary search.")
                sys.exit(1)

            open("_READY", "w").close()

            if not build():
                print("ERROR: Build failed. Cannot continue binary search.")
                sys.exit(1)

        label = f"round-{iteration}"
        app_path = package_and_extract(version, release, args.arch, label=label)
        print(f"\nRunning test criteria against: {app_path}")
        passed = test_criteria(app_path)
        mark_result(label, args.arch, passed)

        if passed:
            print(f"PASS — leak not present with patches [0..{mid}]")
            print(f"  → Culprit is in [{mid + 1}..{hi}]")
            lo = mid + 1
        else:
            print(f"FAIL — leak detected with patches [0..{mid}]")
            print(f"  → Culprit is in [{lo}..{mid}]")
            hi = mid

    print("\n" + "=" * 70)
    print(f"RESULT: The patch introducing the leak is [{lo}]:")
    print(f"  {search_patches[lo]}")
    print("=" * 70)


if __name__ == "__main__":
    main()
