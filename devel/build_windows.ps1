<#
.SYNOPSIS
Build Trace Them as a Windows --onedir executable bundle and Inno Setup installer.
#>
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Virtualenv Python not found at $Python"
}

$Version = (& $Python -c "import trace_them; print(trace_them.__version__)").Trim()
if (-not $Version) {
    throw "Could not determine trace_them.__version__"
}

Write-Host "Building Trace Them $Version (--onedir)..."
if (Test-Path "dist\trace-them") {
    Remove-Item "dist\trace-them" -Recurse -Force
}
if (Test-Path "build\trace-them") {
    Remove-Item "build\trace-them" -Recurse -Force
}

& $Python -m PyInstaller --noconfirm --clean "devel\trace-them.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$ExePath = Join-Path $Root "dist\trace-them\trace-them.exe"
if (-not (Test-Path $ExePath)) {
    throw "Expected executable not found: $ExePath"
}

Write-Host "Smoke testing $ExePath..."
$VersionOut = & $ExePath -v
if ($LASTEXITCODE -ne 0) {
    throw "Executable -v check failed"
}
Write-Host "  -v -> $VersionOut"
$VersionOutLong = & $ExePath --version
if ($LASTEXITCODE -ne 0) {
    throw "Executable --version check failed"
}
Write-Host "  --version -> $VersionOutLong"

$env:TRACE_THEM_CONFIG = Join-Path $Root "build\smoke-config.json"
'{"html_output_dir": "' + (($Root -replace '\\', '\\') + '\\build\\smoke-html') + '", "check_updates": false}' | Set-Content $env:TRACE_THEM_CONFIG -Encoding UTF8
try {
    & $ExePath find --username fixture --site GitHub --offline --no-html --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Executable offline find smoke check failed"
    }
} finally {
    Remove-Item Env:TRACE_THEM_CONFIG -ErrorAction SilentlyContinue
}

if (-not $SkipInstaller) {
    $IsccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) {
        $Cmd = Get-Command iscc -ErrorAction SilentlyContinue
        if ($Cmd) { $Iscc = $Cmd.Source }
    }
    if (-not $Iscc) {
        throw "Inno Setup 6 compiler (ISCC.exe) not found."
    }

    Write-Host "Compiling Inno Setup installer..."
    & $Iscc "/DMyAppVersion=$Version" "devel\installer.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC.exe failed with exit code $LASTEXITCODE"
    }

    $SetupPath = Join-Path $Root "dist\trace-them-setup-$Version.exe"
    if (-not (Test-Path $SetupPath)) {
        throw "Expected installer not found: $SetupPath"
    }

    $SumsPath = Join-Path $Root "dist\SHA256SUMS.txt"
    $Assets = Get-ChildItem (Join-Path $Root "dist") -File |
        Where-Object { $_.Name -match "^(trace-them-setup-.*\.exe|trace_them-.*\.(whl|tar\.gz))$" } |
        Sort-Object Name
    $Lines = foreach ($Asset in $Assets) {
        $Digest = (Get-FileHash $Asset.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$Digest  $($Asset.Name)"
    }
    $Lines | Set-Content $SumsPath -Encoding ASCII
    $Hash = (Get-FileHash $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "Built installer: $SetupPath"
    Write-Host "SHA-256: $Hash"
}
