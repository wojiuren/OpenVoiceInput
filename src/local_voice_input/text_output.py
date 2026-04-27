"""Safe text output helpers for transcription results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Callable


class TextOutputError(RuntimeError):
    """Raised when text cannot be copied or written."""


@dataclass(frozen=True)
class TextOutputResult:
    text: str
    copied_to_clipboard: bool = False
    pasted_to_active_window: bool = False
    restored_clipboard: bool = False
    clipboard_restore_format_count: int = 0
    clipboard_restore_skipped_format_count: int = 0
    text_path: Path | None = None
    srt_path: Path | None = None


@dataclass(frozen=True)
class ClipboardRestoreResult:
    restored: bool
    format_count: int = 0
    skipped_format_count: int = 0

    def __bool__(self) -> bool:
        return self.restored


def copy_to_clipboard(
    text: str,
    clipboard_module=None,
    tk_factory: Callable | None = None,
) -> None:
    if clipboard_module is not None:
        _copy_with_module(text, clipboard_module)
        return
    if tk_factory is None:
        try:
            _copy_with_module(text, _default_clipboard_module())
            return
        except TextOutputError:
            pass
    _copy_with_tk(text, tk_factory or _default_tk_factory)


def read_clipboard_text(clipboard_module=None) -> str:
    module = clipboard_module or _default_clipboard_module()
    try:
        value = module.paste()
    except Exception as exc:
        raise TextOutputError(f"failed to read clipboard text: {exc}") from exc
    return "" if value is None else str(value)


def write_text_file(text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise TextOutputError(f"failed to write text to {path}: {exc}") from exc
    return path


def apply_text_outputs(
    text: str,
    copy: bool = False,
    paste: bool = False,
    restore_clipboard: bool = True,
    text_path: str | Path | None = None,
    clipboard_module=None,
    paste_func: Callable[[], None] | None = None,
    sleep_func: Callable[[float], None] = sleep,
    tk_factory: Callable | None = None,
) -> TextOutputResult:
    copied = False
    pasted = False
    restored = False
    restore_format_count = 0
    restore_skipped_count = 0
    written_path = None
    if text_path is not None:
        written_path = write_text_file(text, text_path)
    if paste:
        restore_result = paste_text_via_clipboard(
            text,
            restore_clipboard=restore_clipboard and not copy,
            clipboard_module=clipboard_module,
            paste_func=paste_func,
            sleep_func=sleep_func,
        )
        restored = restore_result.restored
        restore_format_count = restore_result.format_count
        restore_skipped_count = restore_result.skipped_format_count
        pasted = True
    if copy:
        copy_to_clipboard(text, clipboard_module=clipboard_module, tk_factory=tk_factory)
        copied = True
    return TextOutputResult(
        text=text,
        copied_to_clipboard=copied,
        pasted_to_active_window=pasted,
        restored_clipboard=restored,
        clipboard_restore_format_count=restore_format_count,
        clipboard_restore_skipped_format_count=restore_skipped_count,
        text_path=written_path,
    )


def paste_text_via_clipboard(
    text: str,
    restore_clipboard: bool = True,
    clipboard_module=None,
    paste_func: Callable[[], None] | None = None,
    sleep_func: Callable[[float], None] = sleep,
    restore_delay_s: float = 0.15,
) -> ClipboardRestoreResult:
    module = clipboard_module or _default_clipboard_module()
    snapshot = _snapshot_clipboard(module) if restore_clipboard else None
    copy_to_clipboard(text, clipboard_module=module)
    try:
        (paste_func or _paste_ctrl_v)()
        sleep_func(restore_delay_s)
    except Exception as exc:
        if snapshot is not None:
            try:
                _restore_clipboard(module, snapshot)
            except Exception as restore_exc:
                raise TextOutputError(
                    "failed to paste text into active window: "
                    f"{exc}; also failed to restore clipboard: {restore_exc}"
                ) from exc
        raise TextOutputError(f"failed to paste text into active window: {exc}") from exc
    if snapshot is not None:
        try:
            return _restore_clipboard(module, snapshot)
        except Exception:
            return ClipboardRestoreResult(
                restored=False,
                format_count=getattr(snapshot, "format_count", 0),
                skipped_format_count=getattr(snapshot, "skipped_count", 0),
            )
    return ClipboardRestoreResult(restored=False)


def _default_tk_factory():
    import tkinter

    return tkinter.Tk()


def _import_pyperclip():
    try:
        import pyperclip
    except ImportError as exc:
        raise TextOutputError("missing Python package: pyperclip") from exc
    return pyperclip


def _default_clipboard_module():
    try:
        from .windows_clipboard import WindowsClipboard, is_supported

        if is_supported():
            return WindowsClipboard()
    except Exception:
        pass
    return _import_pyperclip()


def _copy_with_module(text: str, module) -> None:
    try:
        module.copy(text)
    except Exception as exc:
        raise TextOutputError(f"failed to copy text to clipboard: {exc}") from exc


def _copy_with_tk(text: str, factory: Callable) -> None:
    try:
        root = factory()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
    except Exception as exc:
        raise TextOutputError(f"failed to copy text to clipboard: {exc}") from exc


def _paste_ctrl_v() -> None:
    try:
        import keyboard
    except ImportError as exc:
        raise TextOutputError("missing Python package: keyboard") from exc
    if hasattr(keyboard, "press_and_release"):
        keyboard.press_and_release("ctrl+v")
        return
    if hasattr(keyboard, "send"):
        keyboard.send("ctrl+v")
        return
    if hasattr(keyboard, "hotkey"):
        keyboard.hotkey("ctrl", "v")
        return
    raise TextOutputError("keyboard package does not support sending Ctrl+V")


def _snapshot_clipboard(module):
    snapshot = getattr(module, "snapshot", None)
    if snapshot is not None:
        return snapshot()
    return read_clipboard_text(module)


def _restore_clipboard(module, snapshot) -> ClipboardRestoreResult:
    restore = getattr(module, "restore", None)
    if restore is not None:
        restore(snapshot)
        return ClipboardRestoreResult(
            restored=True,
            format_count=getattr(snapshot, "format_count", 0),
            skipped_format_count=getattr(snapshot, "skipped_count", 0),
        )
    copy_to_clipboard(str(snapshot), clipboard_module=module)
    return ClipboardRestoreResult(restored=True, format_count=1)
