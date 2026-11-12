"""macOS status item diagnostic: launches app variants and reports what the window server shows for each.

Run on a macOS machine (including a GitHub Actions macOS runner). Each variant is started as a child
process, left running for a few seconds, then inspected through CoreGraphics for windows owned by the
child at the status bar window level (25). The control variant uses a plain NSStatusItem so a negative
result for the wx variants can be told apart from a machine that cannot show status items at all.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

STATUS_WINDOW_LAYER = 25


def list_windows_for_pid(pid: int) -> list[dict]:
    """Return window info dicts owned by pid, including layer, bounds and on-screen state."""
    import Quartz

    rows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID) or []
    found = []
    for row in rows:
        if int(row.get("kCGWindowOwnerPID", -1)) != pid:
            continue
        bounds = row.get("kCGWindowBounds") or {}
        found.append(
            {
                "owner": str(row.get("kCGWindowOwnerName", "")),
                "layer": int(row.get("kCGWindowLayer", -1)),
                "onscreen": bool(row.get("kCGWindowIsOnscreen", False)),
                "alpha": float(row.get("kCGWindowAlpha", 0.0)),
                "bounds": {k: float(v) for k, v in dict(bounds).items()},
            }
        )
    return found


def list_all_status_windows() -> list[dict]:
    """Return every window at the status bar layer on the machine, to show what other items exist."""
    import Quartz

    rows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID) or []
    out = []
    for row in rows:
        if int(row.get("kCGWindowLayer", -1)) == STATUS_WINDOW_LAYER:
            bounds = row.get("kCGWindowBounds") or {}
            out.append(
                {
                    "owner": str(row.get("kCGWindowOwnerName", "")),
                    "pid": int(row.get("kCGWindowOwnerPID", -1)),
                    "onscreen": bool(row.get("kCGWindowIsOnscreen", False)),
                    "x": float(bounds.get("X", 0)),
                    "width": float(bounds.get("Width", 0)),
                }
            )
    return out


def dump_cocoa_state(tag: str) -> None:
    """Print activation policy and every NSApp window with class, level, visibility and frame."""
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    print(f"[{tag}] activationPolicy={app.activationPolicy()} isActive={app.isActive()} "
          f"isRunning={app.isRunning()}", flush=True)
    for win in app.windows():
        print(f"[{tag}] window class={win.className()} level={win.level()} visible={win.isVisible()} "
              f"frame={win.frame()}", flush=True)


def child_control_pyobjc() -> None:
    """Child: create a plain NSStatusItem through pyobjc and run the Cocoa loop."""
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSSquareStatusItemLength)
    item.button().setTitle_("SS")
    print("control: status item created", flush=True)
    import Foundation

    Foundation.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        3.0, False, lambda _t: dump_cocoa_state("control")
    )
    app.run()


def _wx_icon_setup(late: bool, accessory: bool, keepalive: str = "none") -> None:
    """Child helper: build a wx TaskBarIcon before or after the main loop, with an optional keep-alive.

    keepalive is "none", "frame" (hidden top-level wx.Frame) or "noexit" (SetExitOnFrameDelete(False)).
    """
    import wx
    import wx.adv

    from speak_sync.ui.icon_gen import create_tray_icon

    app = wx.App(False)
    holder: dict = {}
    if keepalive == "frame":
        holder["frame"] = wx.Frame(None, -1, "SpeakSyncHost")
    elif keepalive == "noexit":
        app.SetExitOnFrameDelete(False)

    def make() -> None:
        """Create the status item and report the result."""
        icon_type = wx.adv.TBI_CUSTOM_STATUSITEM
        tb = wx.adv.TaskBarIcon(iconType=icon_type)
        ok = tb.SetIcon(create_tray_icon("idle", 22), "SpeakSync diag")
        holder["tb"] = tb
        print(f"wx status item SetIcon returned {ok}, installed={tb.IsIconInstalled()}", flush=True)

    if accessory:
        import AppKit

        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory
        )
    if late:
        wx.CallLater(500, make)
    else:
        make()
    wx.CallLater(3000, dump_cocoa_state, f"wx late={late} accessory={accessory} keepalive={keepalive}")
    app.MainLoop()


def child_wx_early() -> None:
    """Child: wx status item created before MainLoop, default activation policy."""
    _wx_icon_setup(late=False, accessory=False)


def child_wx_late() -> None:
    """Child: wx status item created from inside MainLoop, default activation policy."""
    _wx_icon_setup(late=True, accessory=False)


def child_wx_late_accessory() -> None:
    """Child: wx status item created inside MainLoop with an Accessory activation policy."""
    _wx_icon_setup(late=True, accessory=True)


def child_wx_early_frame() -> None:
    """Child: status item before MainLoop, with a hidden top-level frame keeping the loop alive."""
    _wx_icon_setup(late=False, accessory=False, keepalive="frame")


def child_wx_early_noexit() -> None:
    """Child: status item before MainLoop, with SetExitOnFrameDelete(False)."""
    _wx_icon_setup(late=False, accessory=False, keepalive="noexit")


def child_wx_late_frame() -> None:
    """Child: status item created inside MainLoop, hidden frame keeping the loop alive."""
    _wx_icon_setup(late=True, accessory=False, keepalive="frame")


def child_wx_late_frame_accessory() -> None:
    """Child: as wx-late-frame but with an Accessory activation policy set first."""
    _wx_icon_setup(late=True, accessory=True, keepalive="frame")


def child_pyobjc_in_wx() -> None:
    """Child: wx app with a hidden frame, status item built directly through pyobjc inside MainLoop."""
    import wx
    import AppKit

    app = wx.App(False)
    frame = wx.Frame(None, -1, "SpeakSyncHost")
    holder: dict = {"frame": frame}

    def make() -> None:
        """Create a plain NSStatusItem while wx owns the Cocoa run loop."""
        item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSSquareStatusItemLength)
        item.button().setTitle_("SS")
        holder["item"] = item
        print("pyobjc item created inside wx loop", flush=True)

    wx.CallLater(500, make)
    wx.CallLater(3000, dump_cocoa_state, "pyobjc-in-wx")
    app.MainLoop()


def child_pyobjc_in_wx_accessory() -> None:
    """Child: as pyobjc-in-wx but forcing the Accessory policy right before creating the item."""
    import wx
    import AppKit

    app = wx.App(False)
    holder: dict = {"frame": wx.Frame(None, -1, "SpeakSyncHost")}

    def make() -> None:
        """Force Accessory policy, then create a plain NSStatusItem."""
        ns_app = AppKit.NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSSquareStatusItemLength)
        item.button().setTitle_("SS")
        holder["item"] = item
        print("pyobjc item created after forcing accessory", flush=True)

    wx.CallLater(500, make)
    wx.CallLater(3000, dump_cocoa_state, "pyobjc-in-wx-accessory")
    app.MainLoop()


def child_control_regular() -> None:
    """Child: plain NSApp.run with a status item but without changing the activation policy."""
    import AppKit
    import Foundation

    app = AppKit.NSApplication.sharedApplication()
    item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSSquareStatusItemLength)
    item.button().setTitle_("SS")
    Foundation.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        3.0, False, lambda _t: dump_cocoa_state("control-regular")
    )
    app.run()


CHILD_VARIANTS = {
    "control-pyobjc": child_control_pyobjc,
    "wx-early": child_wx_early,
    "wx-late": child_wx_late,
    "wx-late-accessory": child_wx_late_accessory,
    "wx-early-frame": child_wx_early_frame,
    "wx-early-noexit": child_wx_early_noexit,
    "wx-late-frame": child_wx_late_frame,
    "wx-late-frame-accessory": child_wx_late_frame_accessory,
    "pyobjc-in-wx": child_pyobjc_in_wx,
    "pyobjc-in-wx-accessory": child_pyobjc_in_wx_accessory,
    "control-regular": child_control_regular,
}


def run_variant(name: str, argv: list[str], env_extra: dict[str, str], wait: float) -> dict:
    """Start one variant, wait, inspect its windows, terminate it and return a result record."""
    env = dict(os.environ)
    env.update(env_extra)
    baseline = len(list_all_status_windows())
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    time.sleep(wait)
    alive = proc.poll() is None
    windows = list_windows_for_pid(proc.pid) if alive else []
    status_windows = [w for w in windows if w["layer"] == STATUS_WINDOW_LAYER]
    system_status = list_all_status_windows()
    # On recent macOS the window server attributes status items to Control Center, so compare counts.
    added = len(system_status) - baseline if alive else 0
    if alive:
        proc.terminate()
    try:
        output, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
    log_file = os.path.expanduser("~/Library/Logs/SpeakSync/speaksync.log")
    app_log = ""
    if name in ("source-app", "frozen-app") and os.path.exists(log_file):
        with open(log_file, encoding="utf-8", errors="replace") as handle:
            app_log = handle.read()[-4000:]
    return {
        "app_log": app_log,
        "variant": name,
        "alive_after_wait": alive,
        "exit_code": proc.returncode,
        "own_windows": windows,
        "own_status_layer_windows": status_windows,
        "has_status_item": bool(status_windows) or added > 0,
        "status_windows_added": added,
        "all_status_layer_windows_on_machine": system_status,
        "output_tail": output[-3000:],
    }


def main() -> int:
    """Parse arguments, run the requested variants and print a JSON report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=sorted(CHILD_VARIANTS))
    parser.add_argument("--app-binary", help="Path to the frozen SpeakSync executable to test too.")
    parser.add_argument("--wait", type=float, default=12.0)
    args = parser.parse_args()

    if args.child:
        CHILD_VARIANTS[args.child]()
        return 0

    results = []
    for name in CHILD_VARIANTS:
        results.append(run_variant(name, [sys.executable, __file__, "--child", name], {}, args.wait))
    results.append(
        run_variant("source-app", [sys.executable, "-m", "speak_sync"], {"SPEAKSYNC_DIAG": "1"}, args.wait)
    )
    if args.app_binary:
        results.append(run_variant("frozen-app", [args.app_binary], {"SPEAKSYNC_DIAG": "1"}, args.wait))
    print(json.dumps(results, indent=2))
    for r in results:
        print(f"SUMMARY {r['variant']}: alive={r['alive_after_wait']} status_item={r['has_status_item']}")
        if r["app_log"]:
            print("APPLOG " + r["variant"] + ":")
            print(r["app_log"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
