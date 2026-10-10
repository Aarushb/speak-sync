"""High-contrast programmatic system tray icon generator for SpeakSync."""

from __future__ import annotations

import wx


def create_tray_bitmap(status_mode: str = "idle", size: int = 32) -> wx.Bitmap:
    """Render a high-contrast 32x32 bitmap representing 'idle', 'syncing', or 'problem'."""
    bmp = wx.Bitmap(size, size, 32)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(18, 24, 34)))
    dc.Clear()

    if status_mode == "syncing":
        border_color = wx.Colour(56, 189, 248)  # High-contrast sky blue
        fill_color = wx.Colour(12, 74, 110)
        glyph = "S"
    elif status_mode == "problem":
        border_color = wx.Colour(251, 191, 36)  # High-contrast amber
        fill_color = wx.Colour(120, 53, 15)
        glyph = "!"
    else:
        border_color = wx.Colour(52, 211, 153)  # High-contrast emerald
        fill_color = wx.Colour(6, 78, 59)
        glyph = "D"

    dc.SetPen(wx.Pen(border_color, 3))
    dc.SetBrush(wx.Brush(fill_color))
    dc.DrawRoundedRectangle(2, 2, size - 4, size - 4, 6)

    font = wx.Font(
        pointSize=max(10, size // 2 - 2),
        family=wx.FONTFAMILY_SWISS,
        style=wx.FONTSTYLE_NORMAL,
        weight=wx.FONTWEIGHT_BOLD,
    )
    dc.SetFont(font)
    dc.SetTextForeground(wx.Colour(255, 255, 255))
    tw, th = dc.GetTextExtent(glyph)
    dc.DrawText(glyph, (size - tw) // 2, (size - th) // 2)

    dc.SelectObject(wx.NullBitmap)
    return bmp


def create_tray_icon(status_mode: str = "idle", size: int = 32) -> wx.Icon:
    """Create a wx.Icon for the system tray representing 'idle', 'syncing', or 'problem'."""
    bmp = create_tray_bitmap(status_mode=status_mode, size=size)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon
