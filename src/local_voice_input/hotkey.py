"""Global hotkey helpers for push-to-talk dictation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class HotkeyError(RuntimeError):
    """Raised when global hotkey handling is unavailable or fails."""


@dataclass(frozen=True)
class HotkeyNames:
    hold_to_talk: str = "caps lock"
    quit: str = "esc"


def normalize_hotkey_name(name: str) -> str:
    return name.strip().lower().replace("_", " ")


class PushToTalkHotkeyRunner:
    """Small wrapper around a keyboard hook implementation.

    The wrapper keeps the rest of the app independent from the concrete hotkey
    package. Tests can pass a fake keyboard object without touching global hooks.
    """

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        names: HotkeyNames | None = None,
        keyboard_module=None,
    ) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.names = names or HotkeyNames()
        self.keyboard = keyboard_module or _import_keyboard()
        self._recording = False

    def run_until_quit(self) -> None:
        hold_key = normalize_hotkey_name(self.names.hold_to_talk)
        quit_key = normalize_hotkey_name(self.names.quit)
        try:
            self.keyboard.on_press_key(hold_key, lambda _event: self._handle_press())
            self.keyboard.on_release_key(hold_key, lambda _event: self._handle_release())
            self.keyboard.wait(quit_key)
        except Exception as exc:
            raise HotkeyError(f"failed to run hotkey listener: {exc}") from exc
        finally:
            unhook_all = getattr(self.keyboard, "unhook_all", None)
            if unhook_all is not None:
                unhook_all()

    def _handle_press(self) -> None:
        if self._recording:
            return
        self._recording = True
        self.on_press()

    def _handle_release(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self.on_release()


def _import_keyboard():
    try:
        import keyboard
    except ImportError as exc:
        raise HotkeyError("missing Python package: keyboard") from exc
    return keyboard
