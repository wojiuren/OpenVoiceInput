# Troubleshooting

This page uses "environment check" for the `doctor` command because the command is meant to diagnose the local setup.

## Run The Environment Check

```powershell
py -m local_voice_input doctor --run-transcribe-smoke
```

This checks Python packages, model files, audio dependencies, input devices, and a non-microphone transcription smoke test.

## Missing Model Files

If the error says `missing model files`, check that these files exist:

```text
models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx
models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tokens.txt
```

The model directory is ignored by Git, so a fresh clone will not include model weights.

For the default model, try the one-command setup path first:

```powershell
py -m local_voice_input download-model sensevoice-small-onnx-int8
```

To see where it would install files without downloading anything:

```powershell
py -m local_voice_input download-model sensevoice-small-onnx-int8 --dry-run
```

## Microphone Works Elsewhere But Not Here

List input devices:

```powershell
py -m local_voice_input devices
```

Then either choose the device in the GUI or test a device ID:

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --json
```

Do not keep several hotkey listeners running at the same time. They can compete for the same device or hotkey.

## Text Is Recognized But Not Pasted

Try clipboard-only mode first. If clipboard-only works, recognition is fine and the problem is the paste path for the target app.

Some apps block simulated paste or run in elevated mode. In that case, copy-only output is safer.

## API Processing Fails

Show the current API provider config:

```powershell
py -m local_voice_input api-provider show
```

Check that the environment variable named by `api_key_env` exists:

```powershell
echo $env:SILICONFLOW_API_KEY
```

The project config should contain the environment variable name, not the secret value itself.
