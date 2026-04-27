import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionError, TranscriptionJob
from local_voice_input.config import RemoteAsrConfig, RemoteAsrProfileConfig
from local_voice_input.model_selector import ModelProfile
from local_voice_input.remote_asr_backend import (
    RemoteAsrBackend,
    RemoteAsrTransportRequest,
    build_remote_asr_request_payload,
    build_remote_asr_transport_request,
    format_remote_asr_error,
    parse_remote_asr_error,
    parse_remote_asr_response,
    remote_asr_transcriptions_url,
)


def remote_profile() -> ModelProfile:
    return ModelProfile(
        model_id="remote-4090-qwen3-asr-1.7b",
        display_name="Remote 4090 Qwen3-ASR 1.7B",
        backend="remote-asr",
        min_ram_gb=0,
        recommended_ram_gb=0,
        task_fit=("file_transcription", "long_form"),
    )


class RemoteAsrBackendPayloadTests(unittest.TestCase):
    def test_build_remote_asr_transport_request_carries_config_boundary(self):
        job = TranscriptionJob(
            source_path=Path("audio") / "lecture.wav",
            task="file_transcription",
            language="zh",
        )
        profile_config = RemoteAsrProfileConfig(
            base_url="http://192.168.1.50:8765/",
            api_key_env="REMOTE_ASR_KEY",
            timeout_s=45,
            connect_timeout_s=3,
            max_audio_mb=50,
            verify_tls=False,
        )

        request = build_remote_asr_transport_request(
            job,
            remote_profile(),
            profile_name="home_4090",
            profile_config=profile_config,
            client_job_id="job-transport",
        )

        self.assertEqual(request.url, "http://192.168.1.50:8765/v1/asr/transcriptions")
        self.assertEqual(request.audio_path, Path("audio") / "lecture.wav")
        self.assertEqual(request.profile_name, "home_4090")
        self.assertEqual(request.api_key_env, "REMOTE_ASR_KEY")
        self.assertEqual(request.timeout_s, 45)
        self.assertEqual(request.connect_timeout_s, 3)
        self.assertEqual(request.max_audio_mb, 50)
        self.assertFalse(request.verify_tls)
        self.assertEqual(request.request_payload["client_job_id"], "job-transport")

    def test_build_remote_asr_request_payload_is_deterministic(self):
        job = TranscriptionJob(
            source_path=Path("audio") / "lecture.wav",
            task="long_form",
            language="zh",
        )

        payload = build_remote_asr_request_payload(
            job,
            remote_profile(),
            client_job_id="job-001",
            timestamp_granularity="none",
        )

        self.assertEqual(
            payload,
            {
                "client_job_id": "job-001",
                "task": "long_form",
                "language": "zh",
                "model_id": "remote-4090-qwen3-asr-1.7b",
                "source_name": "lecture.wav",
                "response_format": "json",
                "timestamp_granularity": "none",
            },
        )

    def test_parse_remote_asr_success_response(self):
        result = parse_remote_asr_response(
            {
                "text": "hello world",
                "model_id": "remote-4090-qwen3-asr-1.7b",
                "language": "en",
                "segments": [
                    {
                        "text": "hello",
                        "start_s": 0,
                        "end_s": "0.5",
                        "speaker": None,
                    }
                ],
                "metadata": {
                    "server_id": "home-4090",
                    "rtf": 0.149,
                },
            }
        )

        self.assertEqual(result.text, "hello world")
        self.assertEqual(result.model_id, "remote-4090-qwen3-asr-1.7b")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.segments[0].text, "hello")
        self.assertEqual(result.segments[0].start_s, 0.0)
        self.assertEqual(result.segments[0].end_s, 0.5)
        self.assertEqual(result.metadata["backend"], "remote-asr")
        self.assertEqual(result.metadata["server_id"], "home-4090")
        self.assertEqual(result.metadata["rtf"], "0.149")

    def test_parse_remote_asr_error_payload(self):
        error = parse_remote_asr_error(
            {
                "error": {
                    "code": "model_unavailable",
                    "message": "Requested model is not loaded.",
                    "retryable": True,
                    "details": {
                        "server_id": "home-4090",
                        "queue_ms": 12,
                    },
                }
            }
        )

        self.assertEqual(error.code, "model_unavailable")
        self.assertEqual(error.message, "Requested model is not loaded.")
        self.assertTrue(error.retryable)
        self.assertEqual(error.details["server_id"], "home-4090")
        self.assertEqual(error.details["queue_ms"], "12")
        self.assertEqual(
            format_remote_asr_error(error),
            "Remote ASR error model_unavailable: Requested model is not loaded. (retryable=true)",
        )

    def test_parse_remote_asr_response_raises_on_error_payload(self):
        with self.assertRaisesRegex(TranscriptionError, "Remote ASR error timeout"):
            parse_remote_asr_response(
                {
                    "error": {
                        "code": "timeout",
                        "message": "Server timed out.",
                        "retryable": True,
                    }
                }
            )

    def test_parse_remote_asr_response_rejects_missing_text(self):
        with self.assertRaisesRegex(TranscriptionError, "missing string field 'text'"):
            parse_remote_asr_response({"model_id": "remote"})

    def test_remote_asr_backend_uses_fake_transport_successfully(self):
        seen_requests: list[RemoteAsrTransportRequest] = []

        def fake_transport(request: RemoteAsrTransportRequest):
            seen_requests.append(request)
            return {
                "text": "远程识别成功",
                "model_id": "remote-4090-qwen3-asr-1.7b",
                "language": "zh",
                "metadata": {"server_id": "home-4090"},
            }

        backend = RemoteAsrBackend(
            remote_asr_config(base_url="http://192.168.1.50:8765"),
            transport=fake_transport,
        )

        result = backend.transcribe_file(
            TranscriptionJob(
                Path("sample.wav"),
                task="file_transcription",
                language="zh",
                metadata={"client_job_id": "job-fake"},
            ),
            remote_profile(),
        )

        self.assertTrue(backend.is_available())
        self.assertEqual(result.text, "远程识别成功")
        self.assertEqual(result.metadata["server_id"], "home-4090")
        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(seen_requests[0].url, "http://192.168.1.50:8765/v1/asr/transcriptions")
        self.assertEqual(seen_requests[0].request_payload["client_job_id"], "job-fake")
        self.assertEqual(seen_requests[0].request_payload["source_name"], "sample.wav")

    def test_remote_asr_backend_maps_fake_transport_error_response(self):
        def fake_transport(_request: RemoteAsrTransportRequest):
            return {
                "error": {
                    "code": "server_busy",
                    "message": "Queue is full.",
                    "retryable": True,
                }
            }

        backend = RemoteAsrBackend(
            remote_asr_config(base_url="http://192.168.1.50:8765"),
            transport=fake_transport,
        )

        with self.assertRaisesRegex(TranscriptionError, "Remote ASR error server_busy"):
            backend.transcribe_file(TranscriptionJob(Path("sample.wav")), remote_profile())

    def test_remote_asr_backend_without_transport_remains_unavailable(self):
        backend = RemoteAsrBackend(remote_asr_config(base_url="http://192.168.1.50:8765"))

        self.assertFalse(backend.is_available())
        self.assertIn("HTTP transport is not implemented", backend.unavailable_reason())

    def test_remote_asr_transcriptions_url_normalizes_slash(self):
        self.assertEqual(
            remote_asr_transcriptions_url("http://127.0.0.1:8765/"),
            "http://127.0.0.1:8765/v1/asr/transcriptions",
        )


def remote_asr_config(*, base_url: str) -> RemoteAsrConfig:
    return RemoteAsrConfig(
        enabled=True,
        profile="home_4090",
        profiles={"home_4090": RemoteAsrProfileConfig(base_url=base_url)},
    )


if __name__ == "__main__":
    unittest.main()
