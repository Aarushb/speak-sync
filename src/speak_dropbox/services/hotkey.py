"""Global hotkey registration and slot query dispatcher (native RegisterHotKey + pynput)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard
    from pynput.keyboard import KeyCode

    _PYNPUT_AVAILABLE = True
except ImportError:
    keyboard = None  # type: ignore[assignment]
    KeyCode = None  # type: ignore[assignment]
    _PYNPUT_AVAILABLE = False

# Win32 / wx hotkey modifier bitmasks
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

DOUBLE_PRESS_THRESHOLD_SECONDS = 0.45

SUPPORTED_MODIFIER_PRESETS: tuple[str, ...] = (
    "Alt+Win",
    "Ctrl+Shift+Win",
    "Ctrl+Alt+Shift",
    "Alt+Shift",
    "Ctrl+Alt",
)


def normalize_modifier_display(modifier_str: str) -> str:
    """Normalize a modifier string into canonical Title+Case form (e.g. 'Alt+Win')."""
    tokens = [
        t.strip().strip("<>").lower()
        for t in modifier_str.replace("-", "+").split("+")
        if t.strip()
    ]
    parts: list[str] = []
    if any(t in ("ctrl", "control") for t in tokens):
        parts.append("Ctrl")
    if "alt" in tokens:
        parts.append("Alt")
    if "shift" in tokens:
        parts.append("Shift")
    if any(t in ("win", "cmd", "super", "meta") for t in tokens):
        parts.append("Win")
    return "+".join(parts) if parts else "Alt+Win"


def parse_hotkey_spec(hotkey_str: str) -> tuple[int, int] | None:
    """Parse a hotkey string like 'Alt+Win+1' or '<alt>+<cmd>+m' into (mod_mask, vk_code)."""
    if not hotkey_str or not hotkey_str.strip():
        return None
    tokens = [
        t.strip().strip("<>").lower()
        for t in hotkey_str.replace("-", "+").split("+")
        if t.strip()
    ]
    if not tokens:
        return None

    mod_mask = 0
    key_token = ""
    for tok in tokens:
        if tok in ("alt",):
            mod_mask |= MOD_ALT
        elif tok in ("ctrl", "control"):
            mod_mask |= MOD_CONTROL
        elif tok in ("shift",):
            mod_mask |= MOD_SHIFT
        elif tok in ("win", "cmd", "super", "meta"):
            mod_mask |= MOD_WIN
        else:
            key_token = tok

    if not key_token or mod_mask == 0:
        return None

    if len(key_token) == 1 and key_token.isdigit():
        return mod_mask, ord(key_token)
    if len(key_token) == 1 and key_token.isalpha():
        return mod_mask, ord(key_token.upper())
    return None


def to_pynput_combo(hotkey_str: str) -> str | None:
    """Convert a hotkey string like 'Alt+Win+1' into pynput format '<alt>+<cmd>+1'."""
    parsed = parse_hotkey_spec(hotkey_str)
    if parsed is None:
        return None
    mod_mask, vk_code = parsed
    parts: list[str] = []
    if mod_mask & MOD_CONTROL:
        parts.append("<ctrl>")
    if mod_mask & MOD_ALT:
        parts.append("<alt>")
    if mod_mask & MOD_SHIFT:
        parts.append("<shift>")
    if mod_mask & MOD_WIN:
        parts.append("<cmd>")
    parts.append(chr(vk_code).lower())
    return "+".join(parts)


if _PYNPUT_AVAILABLE:

    class NormalizedGlobalHotKeys(keyboard.GlobalHotKeys):  # type: ignore[misc]
        """GlobalHotKeys subclass that normalizes Windows virtual key codes when modifiers are held."""

        def canonical(self, key: Any) -> Any:
            k = super().canonical(key)
            vk = getattr(k, "vk", None)
            char = getattr(k, "char", None)
            if vk is not None and char is None:
                if 65 <= vk <= 90:
                    return KeyCode.from_char(chr(vk).lower())
                if 48 <= vk <= 57:
                    return KeyCode.from_char(chr(vk))
            return k

else:
    NormalizedGlobalHotKeys = None


class GlobalHotkeyService:
    """Manages global hotkeys for Slots 1-9, Summary (0), and Manage Sources (M)."""

    def __init__(
        self,
        *,
        on_slot_hotkey: Callable[[int, bool], None],
        on_summary_hotkey: Callable[[], None],
        on_manage_hotkey: Callable[[], None],
        ui_dispatcher: Callable[[Callable[[], None]], Any] | None = None,
    ) -> None:
        self._on_slot_hotkey = on_slot_hotkey
        self._on_summary_hotkey = on_summary_hotkey
        self._on_manage_hotkey = on_manage_hotkey
        self._ui_dispatcher = ui_dispatcher

        self._last_slot_press_time: dict[int, float] = {}
        self._pynput_listener: Any = None
        self._wx_host_frame: Any = None
        self._registered_wx_ids: list[int] = []
        self._active_bindings: dict[str, str] = {}

    @property
    def active_bindings(self) -> dict[str, str]:
        """Return a mapping of action names to human-readable hotkey strings."""
        return dict(self._active_bindings)

    def handle_slot_trigger(self, slot_number: int, *, now: float | None = None) -> bool:
        """Process a slot hotkey press, detecting double-presses for clipboard copy.

        Returns True if this press was a double-press.
        """
        timestamp = now if now is not None else time.monotonic()
        prev_time = self._last_slot_press_time.get(slot_number, -100.0)
        is_double = (timestamp - prev_time) <= DOUBLE_PRESS_THRESHOLD_SECONDS
        self._last_slot_press_time[slot_number] = timestamp

        def _invoke() -> None:
            self._on_slot_hotkey(slot_number, is_double)

        if self._ui_dispatcher is not None:
            self._ui_dispatcher(_invoke)
        else:
            _invoke()
        return is_double

    def handle_summary_trigger(self) -> None:
        if self._ui_dispatcher is not None:
            self._ui_dispatcher(self._on_summary_hotkey)
        else:
            self._on_summary_hotkey()

    def handle_manage_trigger(self) -> None:
        if self._ui_dispatcher is not None:
            self._ui_dispatcher(self._on_manage_hotkey)
        else:
            self._on_manage_hotkey()

    def build_hotkey_map(
        self,
        modifier: str = "Alt+Win",
        summary_hotkey: str = "Alt+Win+0",
        manage_hotkey: str = "Alt+Win+M",
    ) -> dict[str, Callable[[], None]]:
        """Build the mapping of human hotkey specs to callbacks."""
        norm_mod = normalize_modifier_display(modifier)
        bindings: dict[str, Callable[[], None]] = {}
        self._active_bindings.clear()

        for slot_num in range(1, 10):
            spec = f"{norm_mod}+{slot_num}"
            self._active_bindings[f"slot_{slot_num}"] = spec
            bindings[spec] = lambda s=slot_num: self.handle_slot_trigger(s)  # type: ignore[misc]

        sum_spec = summary_hotkey.strip() or f"{norm_mod}+0"
        self._active_bindings["summary"] = sum_spec
        bindings[sum_spec] = self.handle_summary_trigger

        mgr_spec = manage_hotkey.strip() or f"{norm_mod}+M"
        self._active_bindings["manage"] = mgr_spec
        bindings[mgr_spec] = self.handle_manage_trigger

        return bindings

    def start(
        self,
        modifier: str = "Alt+Win",
        summary_hotkey: str = "Alt+Win+0",
        manage_hotkey: str = "Alt+Win+M",
        *,
        wx_module: Any = None,
    ) -> bool:
        """Register global hotkeys via native wx.Frame.RegisterHotKey and/or pynput."""
        self.stop()
        spec_map = self.build_hotkey_map(modifier, summary_hotkey, manage_hotkey)
        registered_any = False

        # 1. Try native OS registration via hidden wx.Frame if wx is active
        if wx_module is not None and wx_module.App.Get() is not None:
            try:
                frame = wx_module.Frame(None, -1, "SpeakDropboxHotkeyHost")
                self._wx_host_frame = frame
                base_id = 7000
                for idx, (spec, callback) in enumerate(spec_map.items()):
                    parsed = parse_hotkey_spec(spec)
                    if parsed is None:
                        continue
                    mod_mask, vk_code = parsed
                    hk_id = base_id + idx
                    if frame.RegisterHotKey(hk_id, mod_mask, vk_code):
                        self._registered_wx_ids.append(hk_id)
                        frame.Bind(
                            wx_module.EVT_HOTKEY,
                            lambda _evt, cb=callback: cb(),
                            id=hk_id,
                        )
                        registered_any = True
            except Exception as exc:
                logger.debug("Native wx RegisterHotKey setup failed: %s", exc)

        # 2. If native registration did not cover all hotkeys, start NormalizedGlobalHotKeys
        if not registered_any and _PYNPUT_AVAILABLE and NormalizedGlobalHotKeys is not None:
            pynput_map: dict[str, Callable[[], None]] = {}
            for spec, callback in spec_map.items():
                combo = to_pynput_combo(spec)
                if combo:
                    pynput_map[combo] = callback
            if pynput_map:
                try:
                    listener = NormalizedGlobalHotKeys(pynput_map)
                    listener.daemon = True
                    listener.start()
                    self._pynput_listener = listener
                    registered_any = True
                except Exception as exc:
                    logger.warning("Failed to start pynput GlobalHotKeys: %s", exc)

        return registered_any

    def stop(self) -> None:
        """Unregister all active global hotkeys and clean up listeners."""
        if self._pynput_listener is not None:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None

        if self._wx_host_frame is not None:
            for hk_id in self._registered_wx_ids:
                try:
                    self._wx_host_frame.UnregisterHotKey(hk_id)
                except Exception:
                    pass
            self._registered_wx_ids.clear()
            try:
                self._wx_host_frame.Destroy()
            except Exception:
                pass
            self._wx_host_frame = None
