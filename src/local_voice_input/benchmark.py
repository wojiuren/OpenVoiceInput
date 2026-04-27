"""Small transcription benchmarks for checking local model fit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Mapping, Sequence

from .app import VoiceInputApp
from .asr import TranscriptionResult
from .model_selector import SelectionRequest
from .sherpa_backend import SENSEVOICE_DIR_NAME, default_model_root


@dataclass(frozen=True)
class BenchmarkCase:
    path: Path
    label: str | None = None


@dataclass(frozen=True)
class BenchmarkResult:
    path: Path
    label: str
    run_index: int
    model_id: str
    language: str
    audio_duration_s: float | None
    elapsed_s: float
    rtf: float | None
    text: str

    @property
    def verdict(self) -> str:
        if self.rtf is None:
            return "unknown"
        if self.rtf <= 0.25:
            return "fast"
        if self.rtf <= 0.75:
            return "usable"
        if self.rtf <= 1.0:
            return "slow"
        return "too_slow"


def default_benchmark_cases() -> tuple[BenchmarkCase, ...]:
    sample = default_model_root() / SENSEVOICE_DIR_NAME / "test_wavs" / "zh.wav"
    return (BenchmarkCase(path=sample, label="sensevoice-zh-sample"),)


def run_transcription_benchmark(
    app: VoiceInputApp,
    cases: Sequence[BenchmarkCase],
    *,
    request: SelectionRequest,
    repeat: int = 1,
) -> tuple[BenchmarkResult, ...]:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    results: list[BenchmarkResult] = []
    for case in cases:
        if not case.path.exists():
            raise FileNotFoundError(case.path)
        for index in range(repeat):
            started = perf_counter()
            transcription = app.transcribe_file(case.path, request=request)
            elapsed_s = perf_counter() - started
            duration_s = _duration_from_result(transcription)
            results.append(
                BenchmarkResult(
                    path=case.path,
                    label=_case_label(case, index, repeat),
                    run_index=index + 1,
                    model_id=transcription.model_id,
                    language=transcription.language,
                    audio_duration_s=duration_s,
                    elapsed_s=elapsed_s,
                    rtf=_rtf(duration_s, elapsed_s),
                    text=transcription.text,
                )
            )
    return tuple(results)


def summarize_benchmark_results(
    results: Sequence[BenchmarkResult],
    *,
    discard_first: bool = False,
) -> dict:
    selected = [result for result in results if not discard_first or result.run_index > 1]
    rtfs = [result.rtf for result in selected if result.rtf is not None]
    elapsed = [result.elapsed_s for result in selected]
    return {
        "count": len(selected),
        "total_count": len(results),
        "discarded_first_count": len(results) - len(selected),
        "avg_elapsed_s": _average(elapsed),
        "avg_rtf": _average(rtfs),
        "worst_rtf": max(rtfs) if rtfs else None,
        "verdict": _overall_verdict(rtfs),
    }


def usage_advice(summary: Mapping[str, object], *, task: str = "file_transcription") -> str:
    avg_rtf = _as_float(summary.get("avg_rtf"))
    worst_rtf = _as_float(summary.get("worst_rtf"))
    effective_rtf = worst_rtf if worst_rtf is not None else avg_rtf
    if effective_rtf is None:
        return "这次还拿不到音频时长，先只能确认能跑通，暂时没法判断适不适合长音频。"
    if effective_rtf <= 0.25:
        if task == "dictation":
            return "适合热键短句输入，作为后台文件转写也没问题。"
        if task == "long_form":
            return "适合后台长音频转写，但正式跑整节课前还是先拿几分钟样例估算总耗时。"
        return "适合后台文件转写，日常短句输入也够快。"
    if effective_rtf <= 0.75:
        if task == "dictation":
            return "适合一般短句输入；如果是长课或长会议，更适合放到后台慢慢跑。"
        if task == "long_form":
            return "可以放到后台跑长音频，但建议先测几分钟样例，别直接整节课开跑。"
        return "适合后台文件转写；如果是长课，先用几分钟样例估算总耗时。"
    if effective_rtf <= 1.0:
        if task == "dictation":
            return "勉强能做短句输入，但手感会偏慢；更适合后台文件转写。"
        if task == "long_form":
            return "只建议后台跑长音频；正式转整节课前一定先做样例测速。"
        return "更适合后台文件转写；不建议直接拿它转整节长课。"
    return "不建议直接转整节长课；优先换更轻的模型，或改放到后台/更强机器上跑。"


def result_to_dict(result: BenchmarkResult, *, include_text: bool = False) -> dict:
    data = {
        "path": str(result.path),
        "label": result.label,
        "run_index": result.run_index,
        "phase": "first" if result.run_index == 1 else "repeat",
        "model_id": result.model_id,
        "language": result.language,
        "audio_duration_s": result.audio_duration_s,
        "elapsed_s": result.elapsed_s,
        "rtf": result.rtf,
        "verdict": result.verdict,
    }
    if include_text:
        data["text"] = result.text
    else:
        data["text_length"] = len(result.text)
    return data


def _case_label(case: BenchmarkCase, index: int, repeat: int) -> str:
    base = case.label or case.path.stem
    if repeat == 1:
        return base
    return f"{base}#{index + 1}"


def _duration_from_result(result: TranscriptionResult) -> float | None:
    raw = result.metadata.get("duration_s")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _rtf(duration_s: float | None, elapsed_s: float) -> float | None:
    if duration_s is None or duration_s <= 0:
        return None
    return elapsed_s / duration_s


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _overall_verdict(rtfs: Sequence[float]) -> str:
    if not rtfs:
        return "unknown"
    worst = max(rtfs)
    if worst <= 0.25:
        return "fast"
    if worst <= 0.75:
        return "usable"
    if worst <= 1.0:
        return "slow"
    return "too_slow"


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
