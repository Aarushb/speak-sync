"""Unit tests for GlobalHotkeyService, hotkey parsing, and double-press detection."""

from __future__ import annotations

from speak_dropbox.services.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    GlobalHotkeyService,
    normalize_modifier_display,
    parse_hotkey_spec,
    to_pynput_combo,
)


def test_parse_hotkey_spec_and_pynput_conversion() -> None:
    assert parse_hotkey_spec("Alt+Win+1") == (MOD_ALT | MOD_WIN, ord("1"))
    assert parse_hotkey_spec("<ctrl>+<shift>+<cmd>+m") == (
        MOD_CONTROL | MOD_SHIFT | MOD_WIN,
        ord("M"),
    )
    assert parse_hotkey_spec("invalid") is None

    assert to_pynput_combo("Alt+Win+1") == "<alt>+<cmd>+1"
    assert to_pynput_combo("Ctrl+Shift+Win+M") == "<ctrl>+<shift>+<cmd>+m"
    assert normalize_modifier_display("<alt>+<cmd>") == "Alt+Win"


def test_global_hotkey_service_single_and_double_press() -> None:
    slot_calls: list[tuple[int, bool]] = []
    summary_calls: list[int] = []
    manage_calls: list[int] = []

    svc = GlobalHotkeyService(
        on_slot_hotkey=lambda slot, is_double: slot_calls.append((slot, is_double)),
        on_summary_hotkey=lambda: summary_calls.append(1),
        on_manage_hotkey=lambda: manage_calls.append(1),
    )

    bindings = svc.build_hotkey_map("Alt+Win", "Alt+Win+0", "Alt+Win+M")
    assert "Alt+Win+1" in bindings
    assert "Alt+Win+9" in bindings
    assert "Alt+Win+0" in bindings
    assert "Alt+Win+M" in bindings

    # First press at t=10.0 -> single press (is_double=False)
    assert svc.handle_slot_trigger(1, now=10.0) is False
    assert slot_calls[-1] == (1, False)

    # Second press at t=10.25 (within 0.45s threshold) -> double press (is_double=True)
    assert svc.handle_slot_trigger(1, now=10.25) is True
    assert slot_calls[-1] == (1, True)

    # Third press at t=12.0 (after threshold) -> single press again
    assert svc.handle_slot_trigger(1, now=12.0) is False
    assert slot_calls[-1] == (1, False)

    svc.handle_summary_trigger()
    assert len(summary_calls) == 1

    svc.handle_manage_trigger()
    assert len(manage_calls) == 1
