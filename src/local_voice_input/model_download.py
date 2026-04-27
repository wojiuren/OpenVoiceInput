"""Helpers for installing default local model assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

from .sherpa_backend import SENSEVOICE_DIR_NAME, SENSEVOICE_INT8_DIR_NAME, SenseVoiceModelFiles, default_model_root


DEFAULT_SENSEVOICE_MODEL_ID = "sensevoice-small-onnx-int8"
DEFAULT_SENSEVOICE_ARCHIVE_NAME = f"{SENSEVOICE_INT8_DIR_NAME}.tar.bz2"
DEFAULT_SENSEVOICE_DOWNLOAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{DEFAULT_SENSEVOICE_ARCHIVE_NAME}"
)


@dataclass(frozen=True)
class ModelInstallPlan:
    model_id: str
    url: str
    model_root: Path
    target_dir: Path
    required_files: tuple[Path, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "url": self.url,
            "model_root": str(self.model_root),
            "target_dir": str(self.target_dir),
            "required_files": [str(path) for path in self.required_files],
        }


@dataclass(frozen=True)
class ModelDownloadResult:
    plan: ModelInstallPlan
    status: str
    archive_path: Path | None
    message: str

    def to_dict(self) -> dict[str, object]:
        data = self.plan.to_dict()
        data.update(
            {
                "status": self.status,
                "archive_path": str(self.archive_path) if self.archive_path else None,
                "message": self.message,
            }
        )
        return data


def sensevoice_install_plan(
    model_root: str | Path | None = None,
    url: str = DEFAULT_SENSEVOICE_DOWNLOAD_URL,
) -> ModelInstallPlan:
    root = Path(model_root) if model_root else default_model_root()
    target_dir = root / SENSEVOICE_DIR_NAME
    return ModelInstallPlan(
        model_id=DEFAULT_SENSEVOICE_MODEL_ID,
        url=url,
        model_root=root,
        target_dir=target_dir,
        required_files=(target_dir / "model.int8.onnx", target_dir / "tokens.txt"),
    )


def sensevoice_setup_command() -> str:
    return f"py -m local_voice_input download-model {DEFAULT_SENSEVOICE_MODEL_ID}"


def sensevoice_setup_hint() -> str:
    return f"run `{sensevoice_setup_command()}` to download the default model"


def download_sensevoice_model(
    model_root: str | Path | None = None,
    *,
    url: str = DEFAULT_SENSEVOICE_DOWNLOAD_URL,
    force: bool = False,
    keep_archive: bool = False,
) -> ModelDownloadResult:
    plan = sensevoice_install_plan(model_root=model_root, url=url)
    files = SenseVoiceModelFiles.discover(plan.model_root)
    if not force and not files.missing_paths():
        return ModelDownloadResult(
            plan=plan,
            status="already_installed",
            archive_path=None,
            message=f"model already installed: {files.model.parent}",
        )

    plan.model_root.mkdir(parents=True, exist_ok=True)
    archive_path = plan.model_root / _archive_name_from_url(url)
    _download_file(url, archive_path)

    with tempfile.TemporaryDirectory(prefix="openvoiceinput-model-", dir=str(plan.model_root)) as temp_dir:
        extract_dir = Path(temp_dir)
        _extract_tar_safely(archive_path, extract_dir)
        extracted_model = _find_extracted_sensevoice_dir(extract_dir)
        if not extracted_model:
            raise RuntimeError("downloaded archive did not contain SenseVoice model files")

        if plan.target_dir.exists():
            if not force:
                raise RuntimeError(f"target model directory already exists: {plan.target_dir}")
            shutil.rmtree(plan.target_dir)
        shutil.move(str(extracted_model), str(plan.target_dir))

    if not keep_archive:
        archive_path.unlink(missing_ok=True)

    files = SenseVoiceModelFiles.discover(plan.model_root)
    missing = files.missing_paths()
    if missing:
        paths = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"download finished but required files are still missing: {paths}")

    return ModelDownloadResult(
        plan=plan,
        status="installed",
        archive_path=archive_path if keep_archive else None,
        message=f"model installed: {files.model.parent}",
    )


def _archive_name_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return name or DEFAULT_SENSEVOICE_ARCHIVE_NAME


def _download_file(url: str, destination: Path) -> None:
    with urlopen(url, timeout=30) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _extract_tar_safely(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive_path, "r:bz2") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe path in model archive: {member.name}")
        try:
            archive.extractall(destination, filter="data")
        except TypeError:
            archive.extractall(destination)


def _find_extracted_sensevoice_dir(extract_dir: Path) -> Path | None:
    candidates = (
        extract_dir / SENSEVOICE_INT8_DIR_NAME,
        extract_dir / SENSEVOICE_DIR_NAME,
    )
    for candidate in candidates:
        if not SenseVoiceModelFiles.discover(candidate).missing_paths():
            return candidate
    for candidate in extract_dir.iterdir():
        if candidate.is_dir() and not SenseVoiceModelFiles.discover(candidate).missing_paths():
            return candidate
    return None

