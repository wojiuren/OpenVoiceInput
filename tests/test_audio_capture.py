import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.audio_capture import AudioCaptureError, RecordingSession, list_input_devices, record_wav


class FakeAudioChunk(list):
    def copy(self):
        return FakeAudioChunk(self)


class FakeInputStream:
    def __init__(self, parent, samplerate, channels, dtype, device, callback):
        self.parent = parent
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self):
        self.started = True
        self.callback(FakeAudioChunk([[0.1], [0.2]]), 2, None, None)

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self):
        self.recorded = None
        self.wait_called = False

    def query_devices(self):
        return [
            {"name": "Speaker", "max_input_channels": 0, "default_samplerate": 48000},
            {"name": "Mic\r\nName", "max_input_channels": 2, "default_samplerate": 44100},
        ]

    def rec(self, frames, samplerate, channels, dtype, device):
        self.recorded = {
            "frames": frames,
            "samplerate": samplerate,
            "channels": channels,
            "dtype": dtype,
            "device": device,
        }
        return [[0.0]] * frames

    def wait(self):
        self.wait_called = True

    def InputStream(self, samplerate, channels, dtype, device, callback):
        stream = FakeInputStream(self, samplerate, channels, dtype, device, callback)
        self.stream = stream
        return stream


class FakeSoundFile:
    def __init__(self):
        self.written = None

    def write(self, path, audio, sample_rate):
        self.written = {"path": path, "audio": audio, "sample_rate": sample_rate}
        Path(path).write_bytes(b"fake wav")


class AudioCaptureTests(unittest.TestCase):
    def test_list_input_devices_filters_output_only_devices(self):
        devices = list_input_devices(_sounddevice=FakeSoundDevice())

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Mic Name")
        self.assertEqual(devices[0].index, 1)

    def test_record_wav_records_and_writes_file(self):
        sd = FakeSoundDevice()
        sf = FakeSoundFile()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "capture.wav"

            path = record_wav(
                output,
                seconds=0.25,
                sample_rate_hz=16000,
                channels=1,
                device=1,
                _sounddevice=sd,
                _soundfile=sf,
            )

        self.assertEqual(path, output)
        self.assertEqual(sd.recorded["frames"], 4000)
        self.assertEqual(sd.recorded["device"], 1)
        self.assertTrue(sd.wait_called)
        self.assertEqual(sf.written["sample_rate"], 16000)

    def test_record_wav_wraps_capture_errors(self):
        class BrokenSoundDevice(FakeSoundDevice):
            def rec(self, *args, **kwargs):
                raise RuntimeError("no mic")

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(AudioCaptureError):
                record_wav(
                    Path(temp_dir) / "capture.wav",
                    seconds=1,
                    _sounddevice=BrokenSoundDevice(),
                    _soundfile=FakeSoundFile(),
                )

    def test_recording_session_starts_and_writes_on_stop(self):
        sd = FakeSoundDevice()
        sf = FakeSoundFile()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "hold.wav"
            session = RecordingSession(
                output,
                sample_rate_hz=16000,
                channels=1,
                device=1,
                _sounddevice=sd,
                _soundfile=sf,
            )

            session.start()
            path = session.stop()

        self.assertEqual(path, output)
        self.assertEqual(sf.written["path"], str(output))
        self.assertEqual(sf.written["sample_rate"], 16000)
        self.assertFalse(session.is_recording)

    def test_recording_session_requires_start_before_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = RecordingSession(
                Path(temp_dir) / "hold.wav",
                _sounddevice=FakeSoundDevice(),
                _soundfile=FakeSoundFile(),
            )

            with self.assertRaises(AudioCaptureError):
                session.stop()
