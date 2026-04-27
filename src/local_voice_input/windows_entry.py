"""Helpers for Windows file-entry launchers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_SENDTO_SCRIPT_NAME = "OpenVoiceInput Transcribe.cmd"
DEFAULT_STARTUP_SCRIPT_NAME = "OpenVoiceInput GUI.vbs"


@dataclass(frozen=True)
class TranscribeLauncherOptions:
    cwd: Path
    python_command: str = "py"
    language: str | None = None
    text_out_dir: str | Path | None = "transcripts"
    srt_out_dir: str | Path | None = None
    quick_note: bool = False
    api_process: bool = False
    api_preset: str | None = "clean"
    api_fallback_raw: bool = False
    no_log: bool = False
    pause: bool = True


@dataclass(frozen=True)
class GuiAutostartOptions:
    cwd: Path
    pythonw_command: str = "pyw"
    config_path: Path | None = None


def default_sendto_dir(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    appdata = env.get("APPDATA")
    if not appdata:
        raise ValueError("APPDATA is not set; cannot locate the Windows SendTo folder")
    return Path(appdata) / "Microsoft" / "Windows" / "SendTo"


def default_startup_dir(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    appdata = env.get("APPDATA")
    if not appdata:
        raise ValueError("APPDATA is not set; cannot locate the Windows Startup folder")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def resolve_sendto_script_path(
    output: str | Path | None = None,
    *,
    name: str = DEFAULT_SENDTO_SCRIPT_NAME,
    environ: dict[str, str] | None = None,
) -> Path:
    if output is None:
        return default_sendto_dir(environ) / name
    path = Path(output)
    if path.suffix.lower() in {".cmd", ".bat"}:
        return path
    return path / name


def resolve_startup_script_path(
    output: str | Path | None = None,
    *,
    name: str = DEFAULT_STARTUP_SCRIPT_NAME,
    environ: dict[str, str] | None = None,
) -> Path:
    if output is None:
        return default_startup_dir(environ) / name
    path = Path(output)
    if path.suffix.lower() in {".vbs", ".cmd", ".bat"}:
        return path
    return path / name


def build_transcribe_launcher(options: TranscribeLauncherOptions) -> str:
    args = ["-m", "local_voice_input", "transcribe", "%*"]
    if options.language:
        args.extend(["--language", _cmd_quote(options.language)])
    if options.text_out_dir:
        args.extend(["--text-out-dir", _cmd_quote(str(options.text_out_dir))])
    if options.srt_out_dir:
        args.extend(["--srt-out-dir", _cmd_quote(str(options.srt_out_dir))])
    if options.quick_note:
        args.append("--quick-note")
    if options.api_process:
        args.append("--api-process")
        if options.api_preset:
            args.extend(["--api-preset", _cmd_quote(options.api_preset)])
        if options.api_fallback_raw:
            args.append("--api-fallback-raw")
    if options.no_log:
        args.append("--no-log")

    command = " ".join([_cmd_command(options.python_command), *args])
    lines = [
        "@echo off",
        "setlocal",
        f"cd /d {_cmd_quote(str(options.cwd))}",
        command,
        "set exit_code=%ERRORLEVEL%",
    ]
    if options.pause:
        lines.extend(
            [
                "echo.",
                "echo Done. Press any key to close this window.",
                "pause >nul",
            ]
        )
    lines.append("exit /b %exit_code%")
    return "\r\n".join(lines) + "\r\n"


def build_gui_autostart_launcher(options: GuiAutostartOptions) -> str:
    args = ["-m", "local_voice_input", "gui"]
    if options.config_path is not None:
        args.extend(["--config", str(options.config_path)])
    command = " ".join([options.pythonw_command, *(_vbs_escape_arg(arg) for arg in args)])
    lines = [
        'Set WshShell = CreateObject("WScript.Shell")',
        f'WshShell.CurrentDirectory = "{_vbs_escape(str(options.cwd))}"',
        f'WshShell.Run "{_vbs_escape(command)}", 0, False',
    ]
    return "\r\n".join(lines) + "\r\n"


def write_transcribe_launcher(
    path: str | Path,
    options: TranscribeLauncherOptions,
    *,
    overwrite: bool = False,
) -> Path:
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} already exists; pass overwrite=True to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_transcribe_launcher(options), encoding="utf-8", newline="")
    return destination


def write_gui_autostart_launcher(
    path: str | Path,
    options: GuiAutostartOptions,
    *,
    overwrite: bool = False,
) -> Path:
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} already exists; pass overwrite=True to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_gui_autostart_launcher(options), encoding="utf-8", newline="")
    return destination


def remove_gui_autostart_launcher(path: str | Path) -> bool:
    destination = Path(path)
    if not destination.exists():
        return False
    destination.unlink()
    return True


def _cmd_command(value: str) -> str:
    return _cmd_quote(value) if _needs_quotes(value) else value


def _cmd_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _needs_quotes(value: str) -> bool:
    return any(char.isspace() for char in value) or any(char in value for char in "&()[]{}^=;!'+,`~")


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


def _vbs_escape_arg(value: str) -> str:
    if _needs_quotes(value):
        return f'"{value}"'
    return value
