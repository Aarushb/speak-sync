"""Build script for SpeakSync Windows binaries (Portable ZIP & Inno Setup Installer)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"
PACKAGING_DIR = REPO_ROOT / "packaging" / "windows"
SPEC_FILE = PACKAGING_DIR / "speaksync.spec"
ISS_FILE = PACKAGING_DIR / "speaksync.iss"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_inno_setup_compiler() -> Path | None:
    # 1. Check PATH
    which_iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
    if which_iscc:
        return Path(which_iscc)

    # 2. Check standard installation directories
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LocalAppData", r"C:\Users\Default\AppData\Local")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def run_pyinstaller() -> Path:
    print(f"\n[1/3] Running PyInstaller for SpeakSync v{VERSION}...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
    ]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)

    app_dir = DIST_DIR / "speaksync"
    exe_file = app_dir / "speaksync.exe"
    if not exe_file.is_file():
        raise RuntimeError(f"PyInstaller failed to generate expected executable at: {exe_file}")

    # Ensure top-level assets folder is also present alongside speaksync.exe
    target_assets = app_dir / "assets"
    source_assets = REPO_ROOT / "assets"
    if source_assets.is_dir() and not target_assets.is_dir():
        shutil.copytree(source_assets, target_assets)

    print(f"PyInstaller output generated at: {app_dir}")
    print(f"Main executable: {exe_file} ({exe_file.stat().st_size:,} bytes)")
    return app_dir


def create_portable_zip(app_dir: Path) -> Path:
    print(f"\n[2/3] Creating Portable ZIP archive...")
    zip_name = f"SpeakSync-v{VERSION}-windows-portable.zip"
    zip_path = DIST_DIR / zip_name

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include README.md in root
        readme = REPO_ROOT / "README.md"
        if readme.is_file():
            zf.write(readme, arcname="README.md")

        # Walk through app_dir and archive all files
        for root, _dirs, files in os.walk(app_dir):
            root_path = Path(root)
            rel_root = root_path.relative_to(DIST_DIR)
            for f in files:
                file_path = root_path / f
                arcname = str(rel_root / f)
                zf.write(file_path, arcname=arcname)

    size = zip_path.stat().st_size
    checksum = sha256_file(zip_path)
    print(f"Portable ZIP created: {zip_path}")
    print(f"Size: {size:,} bytes ({size / (1024 * 1024):.2f} MB)")
    print(f"SHA256: {checksum}")
    return zip_path


def compile_inno_setup() -> Path | None:
    print(f"\n[3/3] Checking for Inno Setup compiler...")
    iscc_path = find_inno_setup_compiler()
    if iscc_path is None:
        print("Note: Inno Setup (ISCC.exe) was not found on this machine.")
        print("Portable ZIP has been successfully generated.")
        print("The Windows Installer (.exe setup) will be compiled automatically in GitHub Actions CI.")
        return None

    print(f"Found Inno Setup compiler: {iscc_path}")
    cmd = [str(iscc_path), str(ISS_FILE)]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PACKAGING_DIR), check=True)

    setup_exe = DIST_DIR / f"SpeakSync-v{VERSION}-windows-setup.exe"
    if not setup_exe.is_file():
        raise RuntimeError(f"Inno Setup completed but {setup_exe} was not found.")

    size = setup_exe.stat().st_size
    checksum = sha256_file(setup_exe)
    print(f"\nWindows Installer created: {setup_exe}")
    print(f"Size: {size:,} bytes ({size / (1024 * 1024):.2f} MB)")
    print(f"SHA256: {checksum}")
    return setup_exe


def main() -> int:
    print("=" * 60)
    print(f" SpeakSync v{VERSION} - Windows Packaging Pipeline")
    print("=" * 60)

    try:
        app_dir = run_pyinstaller()
        create_portable_zip(app_dir)
        compile_inno_setup()
        print("\nBuild completed successfully!")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"\nERROR: Build command failed with exit code {exc.returncode}")
        return exc.returncode
    except Exception as exc:
        print(f"\nERROR: Build failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
