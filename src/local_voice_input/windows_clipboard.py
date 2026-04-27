"""Windows native clipboard snapshot and restore helpers."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os


class WindowsClipboardError(RuntimeError):
    """Raised when the Windows clipboard API fails."""


GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
CF_UNICODETEXT = 13


user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None

if os.name == "nt":
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t


@dataclass(frozen=True)
class ClipboardFormatData:
    format_id: int
    data: bytes


@dataclass(frozen=True)
class ClipboardSnapshot:
    formats: tuple[ClipboardFormatData, ...]
    skipped_formats: tuple[int, ...] = ()

    @property
    def format_count(self) -> int:
        return len(self.formats)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_formats)


class WindowsClipboard:
    """A pyperclip-like clipboard object with full-format snapshots."""

    def copy(self, text: str) -> None:
        set_clipboard_text(text)

    def paste(self) -> str:
        return get_clipboard_text()

    def snapshot(self) -> ClipboardSnapshot:
        return snapshot_clipboard()

    def restore(self, snapshot: ClipboardSnapshot) -> None:
        restore_clipboard(snapshot)


def is_supported() -> bool:
    return os.name == "nt"


def get_clipboard_text() -> str:
    _require_windows()
    with _open_clipboard():
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)


def set_clipboard_text(text: str) -> None:
    _require_windows()
    data = text.encode("utf-16-le") + b"\x00\x00"
    with _open_clipboard():
        if not user32.EmptyClipboard():
            _raise_last_error("EmptyClipboard")
        _set_clipboard_bytes(CF_UNICODETEXT, data)


def snapshot_clipboard() -> ClipboardSnapshot:
    _require_windows()
    formats: list[ClipboardFormatData] = []
    skipped: list[int] = []
    with _open_clipboard():
        format_id = 0
        while True:
            format_id = user32.EnumClipboardFormats(format_id)
            if format_id == 0:
                break
            data = _get_clipboard_format_bytes(format_id)
            if data is None:
                skipped.append(format_id)
            else:
                formats.append(ClipboardFormatData(format_id=format_id, data=data))
    return ClipboardSnapshot(formats=tuple(formats), skipped_formats=tuple(skipped))


def restore_clipboard(snapshot: ClipboardSnapshot) -> None:
    _require_windows()
    with _open_clipboard():
        if not user32.EmptyClipboard():
            _raise_last_error("EmptyClipboard")
        for item in snapshot.formats:
            _set_clipboard_bytes(item.format_id, item.data)


def _get_clipboard_format_bytes(format_id: int) -> bytes | None:
    handle = user32.GetClipboardData(format_id)
    if not handle:
        return None
    size = kernel32.GlobalSize(handle)
    if not size:
        return None
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, size)
    finally:
        kernel32.GlobalUnlock(handle)


def _set_clipboard_bytes(format_id: int, data: bytes) -> None:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
    if not handle:
        _raise_last_error("GlobalAlloc")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        _raise_last_error("GlobalLock")
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)

    if not user32.SetClipboardData(format_id, handle):
        kernel32.GlobalFree(handle)
        _raise_last_error("SetClipboardData")


class _open_clipboard:
    def __enter__(self):
        if not user32.OpenClipboard(None):
            _raise_last_error("OpenClipboard")
        return self

    def __exit__(self, exc_type, exc, traceback):
        user32.CloseClipboard()
        return False


def _require_windows() -> None:
    if not is_supported():
        raise WindowsClipboardError("Windows clipboard backend is only available on Windows")


def _raise_last_error(action: str) -> None:
    error = ctypes.get_last_error()
    raise WindowsClipboardError(f"{action} failed with Windows error {error}")
