"""Tests that the app keeps a hidden top-level window so the wx main loop does not end at once."""

import wx

from speak_sync.__main__ import create_host_frame


def test_host_frame_is_top_level_and_hidden(wx_app: wx.App) -> None:
    """The keep-alive frame must count as a top-level window without being shown."""
    frame = create_host_frame()
    try:
        assert frame in wx.GetTopLevelWindows()
        assert not frame.IsShown()
    finally:
        frame.Destroy()
