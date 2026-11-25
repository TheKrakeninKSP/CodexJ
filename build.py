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
PROJECT_ROOT = Path(os.getcwd())
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend"
DIST_DIR = PROJECT_ROOT / "dist"
DEPS_DIR = PROJECT_ROOT / "deps"
RESOURCES_DIR = PROJECT_ROOT / "resources"


def get_version() -> str:
    """Extract version from constants.py using regex (no import needed)"""
    constants_file = BACKEND_DIR / "constants.py"
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

    exe_name = _SINGLEFILE_EXE_NAMES[system]
    exe_path = DEPS_DIR / exe_name

    if exe_path.exists():
        print(f"  SingleFile binary already present: {exe_path}")
        return

    DEPS_DIR.mkdir(exist_ok=True)
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

    exe_name = _FPCALC_EXE_NAMES[system]
    exe_path = DEPS_DIR / exe_name

    if exe_path.exists():
        print(f"  fpcalc binary already present: {exe_path}")
        return

    DEPS_DIR.mkdir(exist_ok=True)
    url = _FPCALC_URLS[system]
    print(f"  Downloading Chromaprint fpcalc v{_CHROMAPRINT_VERSION} from GitHub...")

    archive_path = DEPS_DIR / "fpcalc_archive"
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


# -- ffmpeg / ffprobe (song tagging: yt-dlp -x) -------------------------------
# Static LGPL builds from FFmpeg-Builds (formerly BtbN). That project only publishes
# rolling builds, so this pins the stable release line rather than an exact build.
# LGPL (not GPL) so the binaries can ship inside the app. No macOS builds there: on
# macOS install ffmpeg yourself (e.g. Homebrew) and CodexJ uses it from PATH.

_FFMPEG_LINE = "8.1"
_FFMPEG_BASE = "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/latest"
_FFMPEG_URLS = {
    ("Windows", "x86_64"): f"{_FFMPEG_BASE}/ffmpeg-n{_FFMPEG_LINE}-latest-win64-lgpl-{_FFMPEG_LINE}.zip",
    ("Linux", "x86_64"): f"{_FFMPEG_BASE}/ffmpeg-n{_FFMPEG_LINE}-latest-linux64-lgpl-{_FFMPEG_LINE}.tar.xz",
    ("Linux", "aarch64"): f"{_FFMPEG_BASE}/ffmpeg-n{_FFMPEG_LINE}-latest-linuxarm64-lgpl-{_FFMPEG_LINE}.tar.xz",
}

# -- deno (song tagging: yt-dlp solves YouTube's JS challenges with it) -------

_DENO_VERSION = "2.9.8"
_DENO_TARGETS = {
    ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("Windows", "aarch64"): "aarch64-pc-windows-msvc",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Darwin", "aarch64"): "aarch64-apple-darwin",
}


def _platform_key() -> tuple[str, str]:
    """(OS, normalised CPU arch) for picking a download."""
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return platform.system(), arch


def _exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def _extract_binaries(archive_path: Path, names: list[str]) -> None:
    """Pull the named executables (matched by file name, any folder) out of a .zip or
    .tar.* archive into DEPS_DIR."""
    import tarfile
    import zipfile

    wanted = {_exe(n) for n in names}
    found: set[str] = set()
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                base = member.rsplit("/", 1)[-1]
                if base in wanted and base not in found:
                    (DEPS_DIR / base).write_bytes(zf.read(member))
                    found.add(base)
    else:
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                base = member.name.rsplit("/", 1)[-1]
                if member.isfile() and base in wanted and base not in found:
                    f = tf.extractfile(member)
                    if f:
                        (DEPS_DIR / base).write_bytes(f.read())
                        found.add(base)

    missing = wanted - found
    if missing:
        raise RuntimeError(f"{', '.join(sorted(missing))} not found in {archive_path.name}")
    if platform.system() != "Windows":
        for base in found:
            p = DEPS_DIR / base
            p.chmod(p.stat().st_mode | 0o755)


def _download_archive(url: str, label: str, names: list[str]) -> None:
    import urllib.request

    DEPS_DIR.mkdir(exist_ok=True)
    archive_path = DEPS_DIR / f"{label}_archive"
    print(f"  Downloading {label}...")
    try:
        urllib.request.urlretrieve(url, archive_path)
        _extract_binaries(archive_path, names)
    finally:
        archive_path.unlink(missing_ok=True)
    for n in names:
        size_mb = (DEPS_DIR / _exe(n)).stat().st_size // (1024 * 1024)
        print(f"  {_exe(n)} downloaded ({size_mb}MB)")


def download_ffmpeg() -> None:
    """Download static ffmpeg + ffprobe into deps/ if not present."""
    if all((DEPS_DIR / _exe(n)).exists() for n in ("ffmpeg", "ffprobe")):
        print(f"  ffmpeg/ffprobe already present in {DEPS_DIR}")
        return
    key = _platform_key()
    url = _FFMPEG_URLS.get(key)
    if not url:
        print(f"  No bundled ffmpeg for {key[0]}/{key[1]} - install ffmpeg on PATH for song tagging")
        return
    _download_archive(url, f"ffmpeg {_FFMPEG_LINE}", ["ffmpeg", "ffprobe"])


def download_deno() -> None:
    """Download the deno binary into deps/ if not present."""
    if (DEPS_DIR / _exe("deno")).exists():
        print(f"  deno already present in {DEPS_DIR}")
        return
    key = _platform_key()
    target = _DENO_TARGETS.get(key)
    if not target:
        print(f"  No deno build for {key[0]}/{key[1]} - install deno on PATH for song tagging")
        return
    url = f"https://github.com/denoland/deno/releases/download/v{_DENO_VERSION}/deno-{target}.zip"
    _download_archive(url, f"deno v{_DENO_VERSION}", ["deno"])


def clean_artifacts():
    """Remove previous build artifacts"""
    print("Cleaning build artifacts...")

    dirs_to_clean = [
        DIST_DIR,
        PROJECT_ROOT / "build",
        RESOURCES_DIR / "static",
    ]

    files_to_clean = [
        RESOURCES_DIR / "build_config.py",
        *FRONTEND_DIR.glob("*.tsbuildinfo"),
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
    try:
        subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, env=env, check=True)
    finally:
        # tsc -b incremental caches; stale ones can skip checks on reruns
        for f in FRONTEND_DIR.glob("*.tsbuildinfo"):
            f.unlink()
    print("  Frontend build complete")


def copy_frontend_to_static():
    """Copy built frontend to backend static directory"""
    print("Copying frontend to backend static directory...")

    src = FRONTEND_DIR / "dist"
    dest = RESOURCES_DIR / "static"

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

    config_path = RESOURCES_DIR / "build_config.py"
    config_path.write_text(config_content)
    print(f"  Generated {config_path}")


def run_pyinstaller():
    """Execute PyInstaller with spec file"""
    print("Running PyInstaller...")

    spec_file = PROJECT_ROOT / "codexj.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_file}")

    # Prefer the venv Python (which has PyInstaller installed) over the system Python
    venv_python_win = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    venv_python_unix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python_win.exists():
        python_exe = str(venv_python_win)
    elif venv_python_unix.exists():
        python_exe = str(venv_python_unix)
    else:
        python_exe = sys.executable

    subprocess.run(
        [python_exe, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_file)],
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


def prepare_server_deploy():
    """Build the frontend and fetch helper binaries for a headless/server run from source.

    Unlike the desktop build, this skips build_config.py (the server reads secrets
    from .env, same as dev) and skips PyInstaller entirely - the app runs via
    `python -m backend.serve` against the checked-out source tree.
    """
    build_frontend()
    copy_frontend_to_static()
    download_singlefile()
    download_fpcalc()
    download_ffmpeg()
    download_deno()


def main():
    parser = argparse.ArgumentParser(description="Build CodexJ distribution")
    parser.add_argument(
        "--clean", action="store_true", help="Clean build artifacts first"
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Prepare a headless server deploy (frontend + helper binaries only, "
        "no PyInstaller bundle). Run `python -m backend.serve` afterwards.",
    )
    args = parser.parse_args()

    if args.clean:
        clean_artifacts()

    version = get_version()
    print(f"\n{'='*50}")
    print(f"Building CodexJ v{version}")
    print(f"{'='*50}\n")

    try:
        if args.server:
            prepare_server_deploy()
            print(f"\n{'='*50}")
            print("Server prep complete!")
            print(f"Run with: python -m backend.serve")
            print(f"{'='*50}\n")
        else:
            build_frontend()
            copy_frontend_to_static()
            generate_build_config()
            download_singlefile()
            download_fpcalc()
            download_ffmpeg()
            download_deno()
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
