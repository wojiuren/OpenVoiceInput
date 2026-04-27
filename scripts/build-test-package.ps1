param(
    [string]$Version = "v0.1.0-test.5"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageName = "OpenVoiceInput-MVP-$Version-portable"
$stage = Join-Path $root "dist\$packageName"
$zipPath = Join-Path $root "dist\$packageName.zip"
$git = "C:\Program Files\Git\cmd\git.exe"

if (-not (Test-Path $git)) {
    $git = "git"
}

if (Test-Path $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Force -Path $stage | Out-Null

$sourceTreeZip = Join-Path $root "dist\$packageName-source-tree.zip"
if (Test-Path $sourceTreeZip) {
    Remove-Item -LiteralPath $sourceTreeZip -Force
}

Push-Location $root
try {
    & $git archive --format=zip --output=$sourceTreeZip HEAD
}
finally {
    Pop-Location
}
Expand-Archive -LiteralPath $sourceTreeZip -DestinationPath $stage -Force
Remove-Item -LiteralPath $sourceTreeZip -Force

foreach ($excludedDir in @("captures", "experiments", "tests")) {
    $excludedPath = Join-Path $stage $excludedDir
    if (Test-Path $excludedPath) {
        Remove-Item -LiteralPath $excludedPath -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $stage -Filter "*.cmd" -File | Remove-Item -Force
$gitignorePath = Join-Path $stage ".gitignore"
if (Test-Path $gitignorePath) {
    Remove-Item -LiteralPath $gitignorePath -Force
}

$modelName = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
$modelSource = Join-Path $root "models\$modelName"
$modelDestination = Join-Path $stage "models\$modelName"
New-Item -ItemType Directory -Force -Path $modelDestination | Out-Null

foreach ($modelFile in @("model.int8.onnx", "tokens.txt", "README.md", "LICENSE")) {
    $source = Join-Path $modelSource $modelFile
    if (Test-Path $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $modelDestination $modelFile) -Force
    }
}

$smokeWavSource = Join-Path $modelSource "test_wavs\zh.wav"
if (Test-Path $smokeWavSource) {
    $smokeWavDestination = Join-Path $modelDestination "test_wavs"
    New-Item -ItemType Directory -Force -Path $smokeWavDestination | Out-Null
    Copy-Item -LiteralPath $smokeWavSource -Destination (Join-Path $smokeWavDestination "zh.wav") -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $stage "captures") | Out-Null

$startLauncher = @'
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
title OpenVoiceInput
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -m local_voice_input gui
  endlocal
  exit /b 0
)
py -m local_voice_input gui
if errorlevel 1 (
  echo.
  echo [OpenVoiceInput] Failed to open GUI. Run Install-Dependencies.cmd or Run-Doctor.cmd first.
  pause
)
endlocal
'@

$guiLauncher = @'
@echo off
setlocal
cd /d "%~dp0"
call "%~dp0Start-OpenVoiceInput.cmd"
endlocal
'@

$holdLauncher = @'
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
title OpenVoiceInput - Hold To Talk
echo [OpenVoiceInput] Starting hold-to-talk mode...
echo [OpenVoiceInput] Hold the configured hotkey to record, release to transcribe.
echo [OpenVoiceInput] Press Esc to quit.
echo.
py -m local_voice_input hold-to-talk
if errorlevel 1 (
  echo.
  echo [OpenVoiceInput] Failed to start. Run Install-Dependencies.cmd or Run-Doctor.cmd first.
  pause
)
endlocal
'@

$doctorLauncher = @'
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
title OpenVoiceInput - Doctor
py -m local_voice_input doctor --run-transcribe-smoke
echo.
pause
endlocal
'@

$installLauncher = @'
@echo off
setlocal
cd /d "%~dp0"
title OpenVoiceInput - Install Dependencies
py -m pip install -e ".[all]"
echo.
echo [OpenVoiceInput] If there is no error above, run Run-Doctor.cmd next.
pause
endlocal
'@

$readmeLines = @(
    "OpenVoiceInput-MVP $Version portable test package",
    "",
    "Suggested test order:",
    "",
    "1. Double click: Install-Dependencies.cmd",
    "2. Double click: Run-Doctor.cmd",
    "3. Double click: Start-OpenVoiceInput.cmd",
    "",
    "On the current development machine, dependencies may already be installed, so Run-Doctor.cmd may work first.",
    "",
    "Main entry:",
    "- Start-OpenVoiceInput.cmd opens the GUI. Use this first.",
    "- Open-GUI.cmd is kept as a compatibility alias for older test notes.",
    "- Hold-To-Talk.cmd starts the hotkey mode directly for troubleshooting.",
    "",
    "Included:",
    "- Python source and docs",
    "- Tkinter GUI launcher",
    "- Direct hold-to-talk launcher for troubleshooting",
    "- Required SenseVoice INT8 files: model.int8.onnx + tokens.txt",
    "- SenseVoice smoke-test audio: test_wavs/zh.wav",
    "",
    "Not included:",
    "- User recordings in captures",
    "- Internal local worklogs",
    "- Unit tests",
    "- 1.7B / 4B text post-processing experiment models",
    "- Qwen3-ASR experiment tools",
    "- API key",
    "",
    "If doctor reports missing Python packages, run Install-Dependencies.cmd.",
    "If doctor reports missing model files, check models\$modelName for model.int8.onnx and tokens.txt."
)
$readme = $readmeLines -join [Environment]::NewLine

Set-Content -LiteralPath (Join-Path $stage "Start-OpenVoiceInput.cmd") -Value $startLauncher -Encoding UTF8
Set-Content -LiteralPath (Join-Path $stage "Open-GUI.cmd") -Value $guiLauncher -Encoding UTF8
Set-Content -LiteralPath (Join-Path $stage "Hold-To-Talk.cmd") -Value $holdLauncher -Encoding UTF8
Set-Content -LiteralPath (Join-Path $stage "Run-Doctor.cmd") -Value $doctorLauncher -Encoding UTF8
Set-Content -LiteralPath (Join-Path $stage "Install-Dependencies.cmd") -Value $installLauncher -Encoding UTF8
Set-Content -LiteralPath (Join-Path $stage "README-TEST.txt") -Value $readme -Encoding UTF8

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -CompressionLevel Optimal

$zip = Get-Item -LiteralPath $zipPath
Write-Output "package=$($zip.FullName)"
Write-Output "bytes=$($zip.Length)"
