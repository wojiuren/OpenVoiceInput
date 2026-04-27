# Contributing

OpenVoiceInput-MVP is still an early Windows-focused prototype. Contributions are welcome, but changes should keep the project local-first and privacy-conscious.

## Development Setup

```powershell
py -m pip install -e ".[all]"
py -m local_voice_input doctor --run-transcribe-smoke
py -m unittest discover -s tests
```

The smoke test must not start real microphone recording. Manual microphone checks should be opt-in and clearly documented.

## Before Opening A Pull Request

- Keep user recordings, downloaded models, logs, API keys, and local work notes out of Git.
- Prefer small, testable changes.
- Update public docs when user-facing behavior changes.
- Run focused tests for the changed area, and run the full unit test suite for shared behavior.
- Do not add external network calls to the default dictation path.

## Privacy Expectations

- `captures/`, `models/`, generated experiment outputs, and local worklogs are intentionally ignored.
- API keys should be read from environment variables, not stored in config files.
- Features that send text to external services must be optional and clearly disabled by default.

