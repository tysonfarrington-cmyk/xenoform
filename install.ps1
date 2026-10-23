# Install Xenoform on Windows.
# Creates this folder's own .venv with Python 3.12. It does not pip-install into ComfyUI.
# Pass -LinkNodes to junction the pack into ComfyUI\custom_nodes. That step is off unless you ask.
# Demucs (stem separation, a CPU torch wheel of about 200 MB) is installed by default; pass -NoStems to skip it.
param(
  [switch]$LinkNodes,
  [switch]$NoStems
)
$ErrorActionPreference = "Stop"
$Pack = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python312 {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $exe = $null
    try { $exe = & py -3.12 -c "import sys; print(sys.executable)" 2>$null } catch { $exe = $null }
    if ($LASTEXITCODE -eq 0 -and $exe) {
      return ($exe | Select-Object -Last 1).ToString().Trim()
    }
  }
  foreach ($name in @("python3.12", "python")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $ver = $null
    try { $ver = & $cmd.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { $ver = $null }
    if ($ver -match '^3\.(1[2-9]|[2-9][0-9])$') {
      return $cmd.Source
    }
  }
  # A Python 3.12 that uv manages also works, when uv is on PATH.
  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($uv) {
    $exe = $null
    try { $exe = & $uv.Source python find 3.12 --system 2>$null } catch { $exe = $null }
    if ($LASTEXITCODE -eq 0 -and $exe) {
      return ($exe | Select-Object -Last 1).ToString().Trim()
    }
  }
  return $null
}

$Python312 = Find-Python312
if (-not $Python312) {
  Write-Host "Python 3.12 or newer was not found."
  Write-Host "Install it from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH'."
  Write-Host "This installer does not use ComfyUI's Python."
  exit 1
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "ffmpeg was not found on PATH. The install continues, but Xenoform needs ffmpeg to read songs and write videos."
  Write-Host "Install it (for example: winget install Gyan.FFmpeg), open a new window, and run Xenoform.bat."
}

$Venv = Join-Path $Pack ".venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
  Write-Host "Creating $Venv with $Python312"
  & $Python312 -m venv $Venv
  if (-not (Test-Path $VenvPy)) {
    Write-Host "The virtual environment was not created."
    exit 1
  }
}

Write-Host "Installing Python packages into $Venv"
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -r (Join-Path $Pack "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "pip could not install requirements.txt."; exit 1 }
# The desk runs as `python -m xenoform`, so the package itself has to be in the venv.
& $VenvPy -m pip install --no-deps -e $Pack
if ($LASTEXITCODE -ne 0) { Write-Host "pip could not install the xenoform package."; exit 1 }
# Stems split by default (every loaded song, in the background), so the first Make is stem-reactive. Demucs is the
# `stems` extra in pyproject.toml; on Windows PyPI's torch wheel is the CPU build, which is all Demucs needs here.
if ($NoStems) {
  Write-Host "Skipping Demucs (-NoStems). Stems come from the librosa band split."
} else {
  Write-Host "Installing Demucs for stem separation (a CPU torch wheel; skip it with -NoStems)"
  & $VenvPy -m pip install -e "${Pack}[stems]"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Demucs did not install. The desk still works: stems come from the librosa band split."
    Write-Host "Try again later with: .venv\Scripts\python -m pip install demucs"
  }
}

if ($LinkNodes) {
  $Comfy = $env:COMFYUI_DIR
  $candidates = @(
    (Join-Path $Pack "..\ComfyUI"),
    (Join-Path $env:USERPROFILE "ComfyUI"),
    (Join-Path $env:USERPROFILE "AI\ComfyUI"),
    (Join-Path $env:USERPROFILE "ComfyUI_windows_portable\ComfyUI"),
    (Join-Path $env:USERPROFILE "Desktop\ComfyUI_windows_portable\ComfyUI")
  )
  if (-not $Comfy) {
    foreach ($candidate in $candidates) {
      if (Test-Path (Join-Path $candidate "custom_nodes")) {
        $Comfy = (Resolve-Path $candidate).Path
        break
      }
    }
  }
  if (-not $Comfy) {
    Write-Host "ComfyUI was not found, so the node pack was not linked."
    Write-Host "Set COMFYUI_DIR and run install.ps1 -LinkNodes again."
  } else {
    $Node = Join-Path $Comfy "custom_nodes\xenoform"
    if ((Resolve-Path $Pack).Path -ne $Node) {
      New-Item -ItemType Directory -Force -Path (Join-Path $Comfy "custom_nodes") | Out-Null
      if (Test-Path $Node) {
        Remove-Item $Node -Force -Recurse -ErrorAction SilentlyContinue
      }
      New-Item -ItemType Junction -Path $Node -Target $Pack | Out-Null
      Write-Host "Linked the node pack at $Node"
    }
  }
} else {
  Write-Host "The node pack stays in this folder. Run install.ps1 -LinkNodes if you want it inside ComfyUI custom_nodes."
}

Write-Host ""
Write-Host "Done. Start ComfyUI on http://127.0.0.1:8188 if you want GPU renders, then double-click Xenoform.bat."
Write-Host "It starts comfy-api-proxy on port 8189 if it is not running and opens the desk at http://127.0.0.1:47317"
Write-Host "Press Watch a finished one, then Bundled demo, a vibe, and Make my video."
