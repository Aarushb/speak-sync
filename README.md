# Speak Dropbox

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)
![Platform: Windows | Linux | macOS](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)
![Accessibility: Screen Reader Tested](https://img.shields.io/badge/Accessibility-Screen%20Reader%20Tested-2ea44f.svg)

Speak Dropbox is a screen reader accessible desktop utility that monitors cloud storage and file synchronization clients in the system tray (including the hidden overflow tray on Windows 11 and Windows 10) without moving the mouse or stealing keyboard focus. Inspired by Valiant8086's classic utility, it expands monitoring to Dropbox, Google Drive, Microsoft OneDrive, Resilio Sync, iCloud, Nextcloud, Syncthing, MEGAsync, and any custom tray application.

It provides real-time peripheral awareness through non-intrusive three-stage sync audio cues (`start.flac`, looping `loopty.flac`, and `finish.flac`), direct screen reader and braille output powered by [Prism](https://github.com/ethindp/prism), an accessible system tray context menu, and global slot hotkeys (`Alt+Win+1` through `Alt+Win+9`).

## Quick Start

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[test]"
.venv\Scripts\python.exe -m speak_dropbox
```
