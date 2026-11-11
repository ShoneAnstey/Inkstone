<#
.SYNOPSIS
  Build the Windows binaries locally, with the same steps as the GitHub workflow.

.DESCRIPTION
  PyInstaller cannot cross-compile, so this must run under Windows Python (the
  `py` launcher by default). The source is mirrored to a local Windows folder
  first, because building straight from a \\wsl$ / network path is slow and
  unreliable, and all tooling goes into a private virtual environment there -
  nothing is installed into your global Python.

  From Windows:
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
  From WSL:
    powershell.exe -ExecutionPolicy Bypass -File "$(wslpath -w packaging/build_windows.ps1)" -Commit "$(git rev-parse HEAD)"

  Produces, under <WorkDir>\src\dist:
    Inkstone\            one-dir bundle (what the installer installs; fastest startup)
    Inkstone.exe         portable single file
    Inkstone-Setup.exe   installer - only if Inno Setup (iscc) is installed
  The two .exe files are also copied into this repo's dist\ folder.

.PARAMETER WorkDir
  Where to build. Default: %LOCALAPPDATA%\Inkstone-build (safe to delete).
.PARAMETER Python
  Windows Python used to create the build environment. Default: py
.PARAMETER Commit
  Commit hash to stamp into the build (shown by `Inkstone --version`).
#>
param(
    [string]$WorkDir = (Join-Path $env:LOCALAPPDATA "Inkstone-build"),
    [string]$Python = "py",
    [string]$Commit = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Checked([string]$What, [scriptblock]$Command) {
    Write-Host ">> $What"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $WorkDir "src"
$venv = Join-Path $WorkDir "venv"
$py = Join-Path $venv "Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $src | Out-Null

Write-Host ">> Mirroring source to $src"
# Secrets (env.local, tokens) and private folders are never copied to the build folder.
robocopy $repo $src /MIR /XD .git .venv .build_venv build dist __pycache__ .pytest_cache .ruff_cache .mypy_cache security docs `
    /XF *.pyc build_info.json env.local .env .env.local *.token /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit code $LASTEXITCODE)" }

if (-not (Test-Path $py)) {
    Invoke-Checked "Creating build environment in $venv" { & $Python -m venv $venv }
}
Invoke-Checked "Installing dependencies + PyInstaller" {
    & $py -m pip install --quiet --disable-pip-version-check -r (Join-Path $src "requirements.txt") pyinstaller
}

Push-Location $src
try {
    if (-not $Commit) {
        # Works when git for Windows can read the repo; otherwise the stamp is left blank.
        try { $Commit = (& git -C $repo rev-parse HEAD 2>$null) } catch { $Commit = "" }
    }
    if ($Commit) { $env:GITHUB_SHA = $Commit }
    Write-Host ">> Stamping build metadata"
    $stamp = & $py packaging\stamp_build.py
    if ($LASTEXITCODE -ne 0) { throw "stamp_build.py failed" }
    Write-Host "   $stamp"
    $version = if ("$stamp" -match "version (\S+)\s*$") { $Matches[1] } else { "0.0.0" }

    Invoke-Checked "Building with PyInstaller (one-dir bundle + portable exe)" {
        & $py -m PyInstaller --noconfirm --log-level WARN packaging\inkstone.spec
    }

    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $candidate = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) { $iscc = $candidate }
    }
    if ($iscc) {
        $isccPath = if ($iscc -is [string]) { $iscc } else { $iscc.Source }
        Invoke-Checked "Building installer (Inno Setup)" {
            & $isccPath /Q "/DMyAppVersion=$version" packaging\inkstone_installer.iss
        }
    } else {
        Write-Host ">> Inno Setup (iscc) not found - skipping Inkstone-Setup.exe"
    }
} finally {
    Pop-Location
}

$dist = Join-Path $src "dist"
$repoDist = Join-Path $repo "dist"
New-Item -ItemType Directory -Force -Path $repoDist | Out-Null
foreach ($name in "Inkstone.exe", "Inkstone-Setup.exe") {
    $file = Join-Path $dist $name
    if (Test-Path $file) { Copy-Item $file $repoDist -Force }
}

Write-Host ""
Write-Host "Done."
Write-Host "  One-dir bundle : $(Join-Path $dist 'Inkstone\Inkstone.exe')"
Write-Host "  Portable exe   : $(Join-Path $dist 'Inkstone.exe')"
if (Test-Path (Join-Path $dist "Inkstone-Setup.exe")) {
    Write-Host "  Installer      : $(Join-Path $dist 'Inkstone-Setup.exe')"
}
Write-Host "  (the .exe files were also copied to $repoDist)"
