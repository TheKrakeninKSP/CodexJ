#!/usr/bin/env python3
"""
Build script for CodexJ - creates single executable distribution

Usage:
    python build.py           # Full build
    python build.py --clean   # Clean build artifacts first
"""

import argparse
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = PROJECT_ROOT / "dist"


def get_version() -> str:
    """Extract version from constants.py using regex (no import needed)"""
    constants_file = BACKEND_DIR / "app" / "constants.py"
    content = constants_file.read_text()
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError("Could not find APP_VERSION in constants.py")
    return match.group(1)


def get_npm_command() -> str:
    """Get the correct npm command for the platform"""
    if platform.system() == "Windows":
        return "npm.cmd"
    return "npm"


def get_executable_name() -> str:
    """Get the correct executable name for the platform"""
    if platform.system() == "Windows":
        return "CodexJ.exe"
    return "CodexJ"


_SINGLEFILE_VERSION = "2.0.83"
_SINGLEFILE_URLS = {
    "Windows": f"https://github.com/gildas-lormeau/single-file-cli/releases/download/v{_SINGLEFILE_VERSION}/single-file.exe",
    "Linux": f"https://github.com/gildas-lormeau/single-file-cli/releases/download/v{_SINGLEFILE_VERSION}/single-file-x86_64-linux",
    "Darwin": f"https://github.com/gildas-lormeau/single-file-cli/releases/download/v{_SINGLEFILE_VERSION}/single-file-x86_64-apple-darwin",
}
_SINGLEFILE_EXE_NAMES = {
    "Windows": "single-file.exe",
    "Linux": "single-file",
    "Darwin": "single-file",
}


def download_singlefile() -> None:
    """Download the SingleFile CLI binary into backend/vendor/ if not present."""
    import urllib.request

    system = platform.system()
    if system not in _SINGLEFILE_URLS:
        raise RuntimeError(f"No SingleFile binary available for platform: {system}")

    vendor_dir = BACKEND_DIR / "vendor"
    exe_name = _SINGLEFILE_EXE_NAMES[system]
    exe_path = vendor_dir / exe_name

    if exe_path.exists():
        print(f"  SingleFile binary already present: {exe_path}")
        return

    vendor_dir.mkdir(exist_ok=True)
    url = _SINGLEFILE_URLS[system]
    print(f"  Downloading SingleFile CLI v{_SINGLEFILE_VERSION} from GitHub...")

    urllib.request.urlretrieve(url, exe_path)

    if system != "Windows":
        exe_path.chmod(exe_path.stat().st_mode | 0o755)

    size_mb = exe_path.stat().st_size // (1024 * 1024)
    print(f"  SingleFile CLI downloaded: {exe_path} ({size_mb}MB)")


# -- Chromaprint fpcalc binary ------------------------------------------------

_CHROMAPRINT_VERSION = "1.5.1"
_FPCALC_URLS = {
    "Windows": f"https://github.com/acoustid/chromaprint/releases/download/v{_CHROMAPRINT_VERSION}/chromaprint-fpcalc-{_CHROMAPRINT_VERSION}-windows-x86_64.zip",
    "Linux": f"https://github.com/acoustid/chromaprint/releases/download/v{_CHROMAPRINT_VERSION}/chromaprint-fpcalc-{_CHROMAPRINT_VERSION}-linux-x86_64.tar.gz",
    "Darwin": f"https://github.com/acoustid/chromaprint/releases/download/v{_CHROMAPRINT_VERSION}/chromaprint-fpcalc-{_CHROMAPRINT_VERSION}-macos-universal.tar.gz",
}
_FPCALC_EXE_NAMES = {
    "Windows": "fpcalc.exe",
    "Linux": "fpcalc",
    "Darwin": "fpcalc",
}


def download_fpcalc() -> None:
    """Download the Chromaprint fpcalc binary into backend/vendor/ if not present."""
    import tarfile
    import urllib.request
    import zipfile

    system = platform.system()
    if system not in _FPCALC_URLS:
        raise RuntimeError(f"No fpcalc binary available for platform: {system}")

    vendor_dir = BACKEND_DIR / "vendor"
    exe_name = _FPCALC_EXE_NAMES[system]
    exe_path = vendor_dir / exe_name

    if exe_path.exists():
        print(f"  fpcalc binary already present: {exe_path}")
        return

    vendor_dir.mkdir(exist_ok=True)
    url = _FPCALC_URLS[system]
    print(f"  Downloading Chromaprint fpcalc v{_CHROMAPRINT_VERSION} from GitHub...")

    archive_path = vendor_dir / "fpcalc_archive"
    urllib.request.urlretrieve(url, archive_path)

    # Extract the fpcalc binary from the archive
    if url.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                if member.endswith(exe_name):
                    data = zf.read(member)
                    exe_path.write_bytes(data)
                    break
    else:
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                if member.name.endswith(exe_name):
                    f = tf.extractfile(member)
                    if f:
                        exe_path.write_bytes(f.read())
                    break

    archive_path.unlink(missing_ok=True)

    if not exe_path.exists():
        raise RuntimeError("Failed to extract fpcalc binary from archive")

    if system != "Windows":
        exe_path.chmod(exe_path.stat().st_mode | 0o755)

    size_kb = exe_path.stat().st_size // 1024
    print(f"  fpcalc downloaded: {exe_path} ({size_kb}KB)")


def clean_artifacts():
    """Remove previous build artifacts"""
    print("Cleaning build artifacts...")

    dirs_to_clean = [
        DIST_DIR,
        PROJECT_ROOT / "build",
        BACKEND_DIR / "app" / "static",
    ]

    files_to_clean = [
        BACKEND_DIR / "app" / "build_config.py",
    ]

    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}")

    for f in files_to_clean:
        if f.exists():
            f.unlink()
            print(f"  Removed {f}")


def build_frontend():
    """Build React frontend with production API URL"""
    print("Building frontend...")

    # Set VITE_API_URL to empty for same-origin requests in production
    env = {**os.environ, "VITE_API_URL": ""}

    npm = get_npm_command()

    # Install dependencies if needed
    if not (FRONTEND_DIR / "node_modules").exists():
        print("  Installing npm dependencies...")
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)

    # Build
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, env=env, check=True)
    print("  Frontend build complete")


def copy_frontend_to_static():
    """Copy built frontend to backend static directory"""
    print("Copying frontend to backend static directory...")

    src = FRONTEND_DIR / "dist"
    dest = BACKEND_DIR / "app" / "static"

    if dest.exists():
        shutil.rmtree(dest)

    shutil.copytree(src, dest)
    print(f"  Copied {src} -> {dest}")


def generate_build_config():
    """Generate build_config.py with embedded configuration"""
    print("Generating build configuration...")

    config_content = f'''"""
Auto-generated by build.py - DO NOT COMMIT
Embedded configuration for production build
"""

JWT_SECRET = "{secrets.token_hex(32)}"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7
DB_NAME = "codexj"
MONGODB_URI = "mongodb://localhost:27017/"
'''

    config_path = BACKEND_DIR / "app" / "build_config.py"
    config_path.write_text(config_content)
    print(f"  Generated {config_path}")


def run_pyinstaller():
    """Execute PyInstaller with spec file"""
    print("Running PyInstaller...")

    spec_file = PROJECT_ROOT / "codexj.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_file}")

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_file)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    print("  PyInstaller complete")


def create_release_package(version: str):
    """Create final release directory structure"""
    print(f"Creating release package v{version}...")

    release_dir = DIST_DIR / f"CodexJ_v{version}"

    # Clean existing release dir if present
    if release_dir.exists():
        shutil.rmtree(release_dir)

    release_dir.mkdir(parents=True, exist_ok=True)

    # Copy executable and dependencies from PyInstaller output
    pyinstaller_output = DIST_DIR / "CodexJ"
    if pyinstaller_output.exists():
        # Copy all files from PyInstaller output
        for item in pyinstaller_output.iterdir():
            dest = release_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Remove intermediate PyInstaller directory
        shutil.rmtree(pyinstaller_output)
        print(f"  Cleaned up intermediate build directory")

    # Create required directories
    (release_dir / "media").mkdir(exist_ok=True)
    (release_dir / "dumps").mkdir(exist_ok=True)

    print(f"  Release package created at {release_dir}")
    return release_dir


def main():
    parser = argparse.ArgumentParser(description="Build CodexJ distribution")
    parser.add_argument(
        "--clean", action="store_true", help="Clean build artifacts first"
    )
    args = parser.parse_args()

    if args.clean:
        clean_artifacts()

    version = get_version()
    print(f"\n{'='*50}")
    print(f"Building CodexJ v{version}")
    print(f"{'='*50}\n")

    try:
        build_frontend()
        copy_frontend_to_static()
        generate_build_config()
        download_singlefile()
        download_fpcalc()
        run_pyinstaller()
        release_dir = create_release_package(version)

        print(f"\n{'='*50}")
        print(f"Build complete!")
        print(f"Output: {release_dir}")
        print(f"{'='*50}\n")

    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nBuild failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
