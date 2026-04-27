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
        self._restoring_lock_key = False

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
        if self._restoring_lock_key:
            return
        if self._recording:
            return
        self._recording = True
        self.on_press()

    def _handle_release(self) -> None:
        if self._restoring_lock_key:
            return
        if not self._recording:
            return
        self._recording = False
        self._restore_hold_key_toggle_state()
        self.on_release()

    def _restore_hold_key_toggle_state(self) -> None:
        hold_key = normalize_hotkey_name(self.names.hold_to_talk)
        if hold_key != "caps lock":
            return
        self._restoring_lock_key = True
        try:
            _press_and_release(self.keyboard, hold_key)
        except Exception:
            return
        finally:
            self._restoring_lock_key = False


def _import_keyboard():
    try:
        import keyboard
    except ImportError as exc:
        raise HotkeyError("missing Python package: keyboard") from exc
    return keyboard


def _press_and_release(keyboard_module, key_name: str) -> None:
    press_and_release = getattr(keyboard_module, "press_and_release", None)
    if press_and_release is not None:
        press_and_release(key_name)
        return
    send = getattr(keyboard_module, "send", None)
    if send is not None:
        send(key_name)
