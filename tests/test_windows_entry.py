import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.windows_entry import (
    DEFAULT_STARTUP_SCRIPT_NAME,
    GuiAutostartOptions,
    TranscribeLauncherOptions,
    build_gui_autostart_launcher,
    build_transcribe_launcher,
    default_startup_dir,
    remove_gui_autostart_launcher,
    default_sendto_dir,
    resolve_startup_script_path,
    resolve_sendto_script_path,
    write_gui_autostart_launcher,
    write_transcribe_launcher,
)


class WindowsEntryTests(unittest.TestCase):
    def test_default_sendto_dir_uses_appdata(self):
        path = default_sendto_dir({"APPDATA": r"C:\Users\Example\AppData\Roaming"})

        self.assertEqual(path, Path(r"C:\Users\Example\AppData\Roaming") / "Microsoft" / "Windows" / "SendTo")

    def test_default_startup_dir_uses_appdata(self):
        path = default_startup_dir({"APPDATA": r"C:\Users\Example\AppData\Roaming"})

        self.assertEqual(
            path,
            Path(r"C:\Users\Example\AppData\Roaming") / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
        )

    def test_resolve_sendto_script_path_accepts_directory_or_file(self):
        self.assertEqual(
            resolve_sendto_script_path("launchers", name="Voice.cmd"),
            Path("launchers") / "Voice.cmd",
        )
        self.assertEqual(resolve_sendto_script_path("Voice.cmd"), Path("Voice.cmd"))

    def test_resolve_startup_script_path_accepts_directory_or_file(self):
        self.assertEqual(
            resolve_startup_script_path("launchers", name=DEFAULT_STARTUP_SCRIPT_NAME),
            Path("launchers") / DEFAULT_STARTUP_SCRIPT_NAME,
        )
        self.assertEqual(resolve_startup_script_path("Voice.vbs"), Path("Voice.vbs"))

    def test_build_transcribe_launcher_passes_dragged_files_to_transcribe(self):
        script = build_transcribe_launcher(
            TranscribeLauncherOptions(
                cwd=Path(r"C:\Project With Spaces"),
                language="zh",
                text_out_dir="transcripts",
                srt_out_dir="subtitles",
                quick_note=True,
                api_process=True,
                api_preset="clean",
                api_fallback_raw=True,
                no_log=True,
                pause=False,
            )
        )

        self.assertIn('cd /d "C:\\Project With Spaces"', script)
        self.assertIn("py -m local_voice_input transcribe %*", script)
        self.assertIn('--language "zh"', script)
        self.assertIn('--text-out-dir "transcripts"', script)
        self.assertIn('--srt-out-dir "subtitles"', script)
        self.assertIn("--quick-note", script)
        self.assertIn("--api-process", script)
        self.assertIn("--api-fallback-raw", script)
        self.assertIn("--no-log", script)
        self.assertNotIn("pause >nul", script)

    def test_build_gui_autostart_launcher_uses_hidden_pythonw_run(self):
        script = build_gui_autostart_launcher(
            GuiAutostartOptions(
                cwd=Path(r"C:\Project With Spaces"),
                pythonw_command="pyw",
                config_path=Path(r"C:\Project With Spaces\config.json"),
            )
        )

        self.assertIn('WshShell.CurrentDirectory = "C:\\Project With Spaces"', script)
        self.assertIn('WshShell.Run "pyw -m local_voice_input gui --config ""C:\\Project With Spaces\\config.json"""', script)
        self.assertIn(", 0, False", script)

    def test_write_transcribe_launcher_refuses_to_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Voice.cmd"
            options = TranscribeLauncherOptions(cwd=Path(temp_dir), pause=False)

            write_transcribe_launcher(path, options)

            with self.assertRaises(FileExistsError):
                write_transcribe_launcher(path, options)

    def test_write_and_remove_gui_autostart_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / DEFAULT_STARTUP_SCRIPT_NAME
            options = GuiAutostartOptions(cwd=Path(temp_dir))

            written = write_gui_autostart_launcher(path, options)

            self.assertEqual(written, path)
            self.assertTrue(path.exists())
            self.assertTrue(remove_gui_autostart_launcher(path))
            self.assertFalse(path.exists())
            self.assertFalse(remove_gui_autostart_launcher(path))


if __name__ == "__main__":
    unittest.main()
