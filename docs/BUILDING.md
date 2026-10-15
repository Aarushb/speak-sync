# Building and Packaging SpeakSync

This document describes how to compile, test, package, and distribute SpeakSync across Windows, macOS, and Linux.

---

## Prerequisites

- **Python**: 3.11 or newer (Python 3.12 recommended)
- **uv**: Fast Python package installer and resolver ([docs.astral.sh/uv](https://docs.astral.sh/uv/))
- **Git**: For cloning the repository

SpeakSync strictly scopes all dependencies to isolated virtual environments (`uv venv`) to avoid contaminating system Python installations.

---

## 1. Windows Build (Portable ZIP & Inno Setup Installer)

### Step 1.1: Clone and Set Up Environment

```powershell
git clone https://github.com/Aarushb/speak-sync.git
cd speak-sync

# Create scoped virtual environment
uv venv

# Install SpeakSync in editable mode with test dependencies
uv pip install --python .venv\Scripts\python.exe -e ".[test]"

# Install PyInstaller
uv pip install --python .venv\Scripts\python.exe pyinstaller
```

### Step 1.2: Run the Test Suite

```powershell
.venv\Scripts\pytest.exe
```

This executes the unit tests and the live Windows UI Automation (`IUIAutomation`) accessibility audit to verify that all dialogs and controls expose valid accessibility names and states.

### Step 1.3: Run the Automated Packaging Script

```powershell
.venv\Scripts\python.exe scripts\build_windows.py
```

The script performs the following steps:
1. Compiles the standalone application bundle using PyInstaller and `packaging/windows/speaksync.spec`.
2. Packages `dist/speaksync` into `dist/SpeakSync-v0.1.0-windows-portable.zip` alongside bundled earcons (`assets/start.flac`, `assets/loopty.flac`, `assets/finish.flac`) and documentation.
3. Automatically searches for Inno Setup 6 (`ISCC.exe`) on `PATH` and standard installation directories. If found, it compiles `packaging/windows/speaksync.iss` into `dist/SpeakSync-v0.1.0-windows-setup.exe`.

### Inno Setup Installer Features
- **Per-User Deployment**: Installs to `{localappdata}\Programs\SpeakSync` without requiring administrator privileges or UAC elevation prompts.
- **Autostart Integration**: Includes an option for `"Start SpeakSync when Windows starts"` (checked by default) that writes directly to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. This key is synchronized with the in-app autostart toggle in SpeakSync's system tray menu and settings dialog.
- **Clean Uninstallation**: Automatically removes startup registry keys, shortcuts, and app files on uninstall.

---

## 2. macOS Build (Standalone App Bundle)

### Step 2.1: Clone and Set Up Environment

```bash
git clone https://github.com/Aarushb/speak-sync.git
cd speak-sync

# Create virtual environment
uv venv

# Install dependencies
uv pip install --python .venv/bin/python -e ".[test]"
uv pip install --python .venv/bin/python pyinstaller
```

### Step 2.2: Run Cross-Platform Tests

```bash
.venv/bin/pytest -q tests/test_models.py tests/test_classifier.py tests/test_folders.py tests/test_config.py tests/test_history.py tests/test_cross_platform_backends.py
```

### Step 2.3: Build the `.app` Bundle

```bash
.venv/bin/pyinstaller \
  --name "SpeakSync" \
  --windowed \
  --noconfirm \
  --clean \
  --add-data "assets:assets" \
  --hidden-import "soundobj" \
  --hidden-import "prism" \
  --hidden-import "pynput" \
  --hidden-import "pynput.keyboard._darwin" \
  --hidden-import "pynput.mouse._darwin" \
  src/speak_sync/__main__.py

# Create release zip archive
cd dist
zip -r SpeakSync-v0.1.0-macos.zip SpeakSync.app
```

The generated application bundle is located at `dist/SpeakSync.app`.

---

## 3. Linux Build (Portable Tarball)

### Step 3.1: Install System Libraries

#### Ubuntu / Debian (22.04 / 24.04):
```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  libgtk-3-dev \
  libdbus-1-dev \
  libasound2-dev \
  libpulse-dev
```

#### Fedora / RHEL:
```bash
sudo dnf install -y \
  gtk3-devel \
  dbus-devel \
  alsa-lib-devel \
  pulseaudio-libs-devel
```

### Step 3.2: Set Up Environment and Install Dependencies

```bash
git clone https://github.com/Aarushb/speak-sync.git
cd speak-sync

# Create virtual environment
uv venv

# Install dependencies
uv pip install --python .venv/bin/python -e ".[test]"
uv pip install --python .venv/bin/python pyinstaller
```

### Step 3.3: Run Cross-Platform Tests

```bash
.venv/bin/pytest -q tests/test_models.py tests/test_classifier.py tests/test_folders.py tests/test_config.py tests/test_history.py tests/test_cross_platform_backends.py
```

### Step 3.4: Build the Portable Linux Binary

```bash
.venv/bin/pyinstaller \
  --name "speaksync" \
  --onedir \
  --noconfirm \
  --clean \
  --add-data "assets:assets" \
  --hidden-import "soundobj" \
  --hidden-import "prism" \
  --hidden-import "pynput" \
  --hidden-import "pynput.keyboard._xorg" \
  --hidden-import "pynput.mouse._xorg" \
  src/speak_sync/__main__.py

# Create release tarball
cd dist
tar -czvf SpeakSync-v0.1.0-linux-x86_64.tar.gz speaksync/
```

The compiled application folder is located at `dist/speaksync/`, ready to run via `./speaksync`.

---

## 4. Automated CI/CD Matrix Builds (GitHub Actions)

SpeakSync includes a continuous integration and release matrix pipeline configured in [`.github/workflows/build.yml`](../.github/workflows/build.yml).

On every push to `main` and on tag creation (`v*`), GitHub Actions automatically:
1. Spawns `windows-latest`, `macos-latest`, and `ubuntu-24.04` runners in parallel.
2. Runs the complete test suite on each operating system.
3. Packages:
   - **Windows**: `SpeakSync-Windows-Portable` (`.zip`) and `SpeakSync-Windows-Installer` (`.exe` via Inno Setup).
   - **macOS**: `SpeakSync-macOS-Bundle` (`.zip` containing `SpeakSync.app`).
   - **Linux**: `SpeakSync-Linux-Tarball` (`.tar.gz` containing standalone binary).
4. Publishes build artifacts for immediate download and testing.
