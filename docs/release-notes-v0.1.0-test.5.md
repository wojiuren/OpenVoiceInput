# OpenVoiceInput-MVP v0.1.0-test.5 Release Notes

This is an early portable Windows test build. It is meant for hands-on testing, not as a stable public release.

## Assets

- `OpenVoiceInput-MVP-v0.1.0-test.5-portable.zip`
- `OpenVoiceInput-MVP-v0.1.0-test.5-portable.zip.sha256`
- The exact SHA256 is published beside the final uploaded zip as the `.sha256` asset.

## Main User-Facing Changes

- The packaged test build uses `Start-OpenVoiceInput.cmd` as the main entry point.
- `Open-GUI.cmd` remains as a compatibility alias.
- `Hold-To-Talk.cmd` is kept for direct hotkey troubleshooting.
- The GUI is the intended daily entry point.
- The GUI now includes a `下载默认模型` action for installing the default SenseVoice model from inside the panel.
- Closing the GUI window minimizes the panel; use `退出面板` when you really want to exit.
- The command line remains useful for diagnostics, environment checks, and repeatable tests.
- The package includes the default SenseVoice INT8 model files needed for local smoke testing.
- If model files are missing after a manual checkout or cleanup, run:

  ```powershell
  py -m local_voice_input download-model sensevoice-small-onnx-int8
  ```

## Dictation And Hotkey Behavior

- Hold-to-talk mode can run in the background when started from the GUI.
- `F8` is recommended as the first low-conflict test hotkey.
- `Caps Lock` can still be used, and the app tries to restore the previous Caps Lock state after recording.
- Startup status text now makes it clearer which device, model, language, output strategy, API processing mode, and quick-note mode are active.

## Privacy Defaults

- Temporary dictation audio is discarded by default after transcription.
- Audio retention must be explicitly enabled.
- Model files, recordings, logs, and generated experiment artifacts are ignored by Git.
- API keys should be stored in environment variables, not in config files.
- External API text post-processing is optional and disabled unless configured.

## GUI And Packaging

- The GUI has controls for common dictation settings, API post-processing status, quick-note status, and audio retention.
- API post-processing remains disabled by default; enable it explicitly when testing external cleanup or polishing.
- The portable package includes the SenseVoice INT8 files needed for the basic local smoke test.
- The package does not include user recordings, API keys, local worklogs, downloaded large language models, or generated benchmark results.

## Known Limitations

- This is still a Windows-focused prototype.
- Some target apps may block simulated paste. Clipboard-only output is the fallback path.
- The GUI still needs manual verification on real user apps before a public release.
- Remote ASR and larger local text post-processing models are experimental and not part of the default path.
- The GitHub Release is expected to be marked as a prerelease.

## Suggested Verification Before Publishing

```powershell
py -m unittest discover -s tests
py -m local_voice_input doctor --run-transcribe-smoke
.\scripts\build-test-package.ps1 -Version v0.1.0-test.5
```

The smoke test must not start a real microphone recording. Real microphone testing should be done manually by the user.
