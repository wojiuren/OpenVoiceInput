# OpenVoiceInput-MVP

OpenVoiceInput-MVP is a local-first Windows voice input prototype. It is being built around a simple goal: hold a hotkey, speak, release, and send the recognized text to the active cursor.

The project is still an early test build. The command-line tools are useful for diagnostics and repeatable testing, but the intended daily entry point is the GUI.

## Current Features

- Tkinter GUI entry point for common settings and hotkey mode.
- Hold-to-talk dictation with a configurable hotkey.
- Local offline speech recognition through sherpa-onnx SenseVoice INT8.
- Clipboard paste output that tries to restore the previous clipboard content.
- Optional text-only clipboard output for apps where automatic paste is unreliable.
- Quick note routing by keywords near the beginning of recognized text.
- Optional API text post-processing through OpenAI-compatible chat-completions endpoints.
- Lightweight context packaging for API post-processing, disabled by default.
- File transcription to text and basic SRT output.
- Model and hardware selection helpers.
- Local benchmark helpers for checking whether a model is fast enough before using it on long audio.

## Privacy Defaults

- User recordings in `captures/` are ignored by Git.
- Model files in `models/` are ignored by Git.
- Temporary dictation audio is discarded by default after transcription unless audio retention is enabled.
- API keys are not stored directly in the project config; the config stores environment variable names such as `SILICONFLOW_API_KEY`.
- External API post-processing is optional. When enabled, recognized text is sent to the configured provider.

## Quick Start

Install the project in editable mode with all optional runtime dependencies:

```powershell
py -m pip install -e ".[all]"
```

Run an environment check:

```powershell
py -m local_voice_input doctor --run-transcribe-smoke
```

Open the GUI:

```powershell
py -m local_voice_input gui
```

The packaged test build also includes:

- `Start-OpenVoiceInput.cmd` as the main GUI launcher.
- `Run-Doctor.cmd` for environment checks.
- `Hold-To-Talk.cmd` for direct hotkey troubleshooting.

## Useful Commands

List input devices:

```powershell
py -m local_voice_input devices
```

Record once, transcribe, and print JSON:

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --json
```

Start hold-to-talk mode:

```powershell
py -m local_voice_input hold-to-talk --hold-key f8 --language zh
```

Benchmark the current local model on a small sample before trying long audio:

```powershell
py -m local_voice_input benchmark
```

## Project Docs

- [Getting started](docs/getting-started.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Privacy notes](docs/privacy.md)
- [Model selection](docs/model-selection.md)
- [Release notes](docs/release-notes-v0.1.0-test.5.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

Show model recommendations:

```powershell
py -m local_voice_input recommend --task dictation --language zh
```

## Model Files

The default local ASR path expects the SenseVoice sherpa-onnx model files under:

```text
models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/
```

At minimum, the local backend needs:

- `model.int8.onnx`
- `tokens.txt`

Model weights are not committed to this repository.

## Documentation

Current public-facing documents:

- [Getting started](docs/getting-started.md)
- [Privacy](docs/privacy.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [Requirements](docs/requirements.md)
- [Model selection](docs/model-selection.md)
- [Backend boundary](docs/backend-boundary.md)
- [Draft test release notes](docs/release-notes-v0.1.0-test.5.md)

Internal construction notes, validation checklists, and local automation worklogs are intentionally ignored by Git.

## Development Checks

Run the unit tests:

```powershell
py -m unittest discover -s tests
```

Run the non-microphone smoke test:

```powershell
py -m local_voice_input doctor --run-transcribe-smoke
```

Build a local portable test package:

```powershell
.\scripts\build-test-package.ps1 -Version v0.1.0-test.5
```

## Current Public-Release Status

This repository is not ready to be made public as-is. The current cleanup focus is:

- separate public docs from local construction notes;
- remove stale README language and internal worklog references;
- rebuild and verify the next test package;
- decide whether to publish from a clean-history public repository;
- add GitHub topics, issue labels, and release assets.
