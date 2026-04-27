import unittest

import test_bootstrap  # noqa: F401

from local_voice_input.hotkey import HotkeyNames, PushToTalkHotkeyRunner, normalize_hotkey_name


class FakeKeyboard:
    def __init__(self):
        self.press = None
        self.release = None
        self.waited_for = None
        self.sent = []
        self.unhooked = False

    def on_press_key(self, name, callback):
        self.press = (name, callback)

    def on_release_key(self, name, callback):
        self.release = (name, callback)

    def wait(self, name):
        self.waited_for = name
        self.press[1](None)
        self.press[1](None)
        self.release[1](None)
        self.release[1](None)

    def press_and_release(self, name):
        self.sent.append(name)

    def unhook_all(self):
        self.unhooked = True


class HotkeyTests(unittest.TestCase):
    def test_normalize_hotkey_name(self):
        self.assertEqual(normalize_hotkey_name("caps_lock"), "caps lock")

    def test_push_to_talk_runner_debounces_press_and_release(self):
        events = []
        keyboard = FakeKeyboard()
        runner = PushToTalkHotkeyRunner(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
            names=HotkeyNames(hold_to_talk="caps_lock", quit="esc"),
            keyboard_module=keyboard,
        )

        runner.run_until_quit()

        self.assertEqual(events, ["press", "release"])
        self.assertEqual(keyboard.press[0], "caps lock")
        self.assertEqual(keyboard.release[0], "caps lock")
        self.assertEqual(keyboard.sent, ["caps lock"])
        self.assertEqual(keyboard.waited_for, "esc")
        self.assertTrue(keyboard.unhooked)

    def test_push_to_talk_runner_does_not_restore_non_toggle_key(self):
        events = []
        keyboard = FakeKeyboard()
        runner = PushToTalkHotkeyRunner(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
            names=HotkeyNames(hold_to_talk="f8", quit="esc"),
            keyboard_module=keyboard,
        )

        runner.run_until_quit()

        self.assertEqual(events, ["press", "release"])
        self.assertEqual(keyboard.sent, [])
