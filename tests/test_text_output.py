import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

import test_bootstrap  # noqa: F401

import local_voice_input.text_output as text_output_module
from local_voice_input.text_output import (
    TextOutputError,
    apply_text_outputs,
    copy_to_clipboard,
    paste_text_via_clipboard,
    read_clipboard_text,
    write_text_file,
)


class FakeTkRoot:
    def __init__(self):
        self.events = []
        self.clipboard = None

    def withdraw(self):
        self.events.append("withdraw")

    def clipboard_clear(self):
        self.events.append("clear")
        self.clipboard = ""

    def clipboard_append(self, text):
        self.events.append("append")
        self.clipboard = text

    def update(self):
        self.events.append("update")

    def destroy(self):
        self.events.append("destroy")


class FakeClipboard:
    def __init__(self, text=""):
        self.text = text

    def copy(self, text):
        self.text = text

    def paste(self):
        return self.text


class FakeSnapshot:
    format_count = 3
    skipped_count = 1

    def __init__(self, value):
        self.value = value


class FakeFullClipboard(FakeClipboard):
    def __init__(self, text=""):
        super().__init__(text)
        self.restored = None

    def snapshot(self):
        return FakeSnapshot(self.text)

    def restore(self, snapshot):
        self.restored = snapshot
        self.text = snapshot.value


class BrokenRestoreClipboard(FakeFullClipboard):
    def restore(self, snapshot):
        raise RuntimeError("restore failed")


class TextOutputTests(unittest.TestCase):
    def test_write_text_file_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "result.txt"

            written = write_text_file("你好", path)

            self.assertEqual(written, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "你好")

    def test_copy_to_clipboard_uses_tk_clipboard_methods(self):
        root = FakeTkRoot()

        copy_to_clipboard("hello", tk_factory=lambda: root)

        self.assertEqual(root.clipboard, "hello")
        self.assertEqual(root.events, ["withdraw", "clear", "append", "update", "destroy"])

    def test_copy_to_clipboard_wraps_errors(self):
        def broken_factory():
            raise RuntimeError("no desktop")

        with self.assertRaises(TextOutputError):
            copy_to_clipboard("hello", tk_factory=broken_factory)

    def test_apply_text_outputs_combines_file_and_clipboard(self):
        clipboard = FakeClipboard()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.txt"

            result = apply_text_outputs("done", copy=True, text_path=path, clipboard_module=clipboard)

            self.assertTrue(result.copied_to_clipboard)
            self.assertEqual(result.text_path, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "done")
            self.assertEqual(clipboard.text, "done")

    def test_read_clipboard_text_returns_text(self):
        self.assertEqual(read_clipboard_text(FakeClipboard("old")), "old")

    def test_paste_text_via_clipboard_restores_previous_text(self):
        clipboard = FakeClipboard("old")
        events = []

        restored = paste_text_via_clipboard(
            "new",
            clipboard_module=clipboard,
            paste_func=lambda: events.append(("paste", clipboard.text)),
            sleep_func=lambda _seconds: None,
        )

        self.assertTrue(restored.restored)
        self.assertEqual(restored.format_count, 1)
        self.assertEqual(events, [("paste", "new")])
        self.assertEqual(clipboard.text, "old")

    def test_paste_text_via_clipboard_restores_full_snapshot_when_available(self):
        clipboard = FakeFullClipboard("rich-old")
        events = []

        restored = paste_text_via_clipboard(
            "new",
            clipboard_module=clipboard,
            paste_func=lambda: events.append(("paste", clipboard.text)),
            sleep_func=lambda _seconds: None,
        )

        self.assertTrue(restored.restored)
        self.assertEqual(restored.format_count, 3)
        self.assertEqual(restored.skipped_format_count, 1)
        self.assertEqual(events, [("paste", "new")])
        self.assertEqual(clipboard.text, "rich-old")

    def test_apply_text_outputs_can_paste_and_restore(self):
        clipboard = FakeClipboard("before")
        events = []

        result = apply_text_outputs(
            "voice",
            paste=True,
            clipboard_module=clipboard,
            paste_func=lambda: events.append(clipboard.text),
            sleep_func=lambda _seconds: None,
        )

        self.assertTrue(result.pasted_to_active_window)
        self.assertTrue(result.restored_clipboard)
        self.assertEqual(result.clipboard_restore_format_count, 1)
        self.assertFalse(result.copied_to_clipboard)
        self.assertEqual(events, ["voice"])
        self.assertEqual(clipboard.text, "before")

    def test_paste_failure_still_restores_clipboard(self):
        clipboard = FakeClipboard("before")

        with self.assertRaises(TextOutputError):
            paste_text_via_clipboard(
                "voice",
                clipboard_module=clipboard,
                paste_func=lambda: (_ for _ in ()).throw(RuntimeError("paste failed")),
                sleep_func=lambda _seconds: None,
            )

        self.assertEqual(clipboard.text, "before")

    def test_paste_failure_reports_restore_failure_without_masking_paste_error(self):
        clipboard = BrokenRestoreClipboard("before")

        with self.assertRaisesRegex(TextOutputError, "paste failed.*restore failed"):
            paste_text_via_clipboard(
                "voice",
                clipboard_module=clipboard,
                paste_func=lambda: (_ for _ in ()).throw(RuntimeError("paste failed")),
                sleep_func=lambda _seconds: None,
            )

    def test_successful_paste_tolerates_clipboard_restore_failure(self):
        clipboard = BrokenRestoreClipboard("before")
        events = []

        restored = paste_text_via_clipboard(
            "voice",
            clipboard_module=clipboard,
            paste_func=lambda: events.append(clipboard.text),
            sleep_func=lambda _seconds: None,
        )

        self.assertFalse(restored.restored)
        self.assertEqual(restored.format_count, 3)
        self.assertEqual(restored.skipped_format_count, 1)
        self.assertEqual(events, ["voice"])
        self.assertEqual(clipboard.text, "voice")

    def test_paste_ctrl_v_uses_keyboard_press_and_release(self):
        calls = []
        old_keyboard = sys.modules.get("keyboard")
        sys.modules["keyboard"] = SimpleNamespace(press_and_release=lambda combo: calls.append(combo))
        try:
            text_output_module._paste_ctrl_v()
        finally:
            if old_keyboard is None:
                sys.modules.pop("keyboard", None)
            else:
                sys.modules["keyboard"] = old_keyboard

        self.assertEqual(calls, ["ctrl+v"])
