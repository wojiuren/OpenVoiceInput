# Privacy

OpenVoiceInput-MVP is designed as a local-first voice input prototype.

## Local Audio

- Live microphone recording is only started by user action, such as hold-to-talk or a one-shot recording command.
- Temporary dictation audio is discarded by default after transcription.
- Audio can be kept only when audio retention is explicitly enabled.
- The `captures/` directory is ignored by Git.

## Local Models

- Local ASR model files are stored under `models/`.
- The `models/` directory is ignored by Git.
- Model weights are not included in this repository.

## Clipboard And Text Output

The default dictation flow uses the clipboard to paste text into the active app:

1. take a snapshot of the current clipboard;
2. put recognized text into the clipboard;
3. send paste to the active window;
4. try to restore the previous clipboard content.

Some Windows apps and clipboard formats can still block perfect restoration. Use clipboard-only or manual copy mode if an app behaves badly.

## External API Processing

API post-processing is optional and disabled unless configured.

When API post-processing is enabled:

- recognized text is sent to the configured provider;
- optional recent text context may also be sent if context mode is enabled;
- audio files are not sent by the text post-processing path;
- API keys should be stored in environment variables, not in project files.

Example:

```powershell
$env:SILICONFLOW_API_KEY="your-api-key"
py -m local_voice_input api-provider set --provider siliconflow --api-key-env SILICONFLOW_API_KEY
```

Do not commit API keys, personal recordings, or private configuration files.

