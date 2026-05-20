# Launch a CloakBrowser stealth Chromium with CDP exposed for browser-harness.
# Windows equivalent of start-cloak.sh — no xvfb needed (native GUI).
#
# Usage:
#   .\start-cloak.ps1                       # default persona
#   .\start-cloak.ps1 -Persona alice        # named persona (own profile + fingerprint)
#   $env:PERSONA='alice'; .\start-cloak.ps1 # same
#
# Personas isolate cookies, localStorage, IndexedDB, and the per-launch
# fingerprint seed. Reusing the same persona across runs preserves the
# "this user has been here before" signal.
#
# Environment overrides:
#   CDP_PORT             default 9222
#   CLOAK_PROFILE        override profile dir
#   FINGERPRINT          force a specific seed (otherwise generated once per persona)
#   FINGERPRINT_PLATFORM default 'windows'
#   CLOAK_BIN            skip Python lookup, point at the cloak binary directly
#   CLOAK_PYTHON         python.exe to import cloakbrowser from
#                        (default: %USERPROFILE%\.cloak-harness\venv\Scripts\python.exe,
#                         then `py -3`, then `python`)

[CmdletBinding()]
param(
    [string]$Persona = $(if ($env:PERSONA) { $env:PERSONA } else { 'default' })
)

$ErrorActionPreference = 'Stop'

$CdpPort             = if ($env:CDP_PORT) { $env:CDP_PORT } else { '9222' }
$PersonaDir          = Join-Path $env:USERPROFILE ".cloak-harness\personas\$Persona"
$ProfileDir          = if ($env:CLOAK_PROFILE) { $env:CLOAK_PROFILE } else { Join-Path $PersonaDir 'profile' }
$FingerprintFile     = Join-Path $PersonaDir 'fingerprint'
$FingerprintPlatform = if ($env:FINGERPRINT_PLATFORM) { $env:FINGERPRINT_PLATFORM } else { 'windows' }

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

# Stable fingerprint per persona — generated once, reused on subsequent launches
# so the same persona always looks like the same machine.
if (Test-Path $FingerprintFile) {
    $Fingerprint = (Get-Content $FingerprintFile -Raw).Trim()
} else {
    $Fingerprint = if ($env:FINGERPRINT) { $env:FINGERPRINT } else { (Get-Random -Maximum 99999).ToString() }
    Set-Content -Path $FingerprintFile -Value $Fingerprint -Encoding ascii
}

function Resolve-CloakBinary {
    if ($env:CLOAK_BIN) { return $env:CLOAK_BIN }

    $candidates = @()
    if ($env:CLOAK_PYTHON) { $candidates += $env:CLOAK_PYTHON }
    $candidates += (Join-Path $env:USERPROFILE '.cloak-harness\venv\Scripts\python.exe')
    $candidates += 'py'
    $candidates += 'python'

    # ensure_binary() downloads the ~200MB stealth Chromium on first run, then
    # binary_info()['binary_path'] returns the cached path. Idempotent.
    $probe = "from cloakbrowser import ensure_binary, binary_info; ensure_binary(); print(binary_info()['binary_path'])"

    foreach ($py in $candidates) {
        $exe = $null
        $pyArgs = $null
        if ($py -eq 'py') {
            $cmd = Get-Command py -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            $exe = $cmd.Source
            $pyArgs = @('-3', '-c', $probe)
        } elseif ($py -eq 'python') {
            $cmd = Get-Command python -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            $exe = $cmd.Source
            $pyArgs = @('-c', $probe)
        } else {
            if (-not (Test-Path $py)) { continue }
            $exe = $py
            $pyArgs = @('-c', $probe)
        }
        $out = & $exe @pyArgs 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    }

    Write-Error @"
Could not import cloakbrowser. Either:
  1. pip install cloakbrowser into a venv at %USERPROFILE%\.cloak-harness\venv, or
  2. set `$env:CLOAK_PYTHON to a python.exe that has cloakbrowser installed, or
  3. set `$env:CLOAK_BIN directly to the stealth Chromium executable path.
"@
}

$Bin = Resolve-CloakBinary

$ChromiumArgs = @(
    '--no-sandbox'
    "--fingerprint=$Fingerprint"
    "--fingerprint-platform=$FingerprintPlatform"
    '--ignore-gpu-blocklist'
    "--remote-debugging-port=$CdpPort"
    '--remote-debugging-address=127.0.0.1'
    "--user-data-dir=$Profile"
    '--window-size=1920,1080'
)

Write-Host "[cloak-harness] persona:     $Persona"
Write-Host "[cloak-harness] binary:      $Bin"
Write-Host "[cloak-harness] CDP:         127.0.0.1:$CdpPort"
Write-Host "[cloak-harness] profile:     $Profile"
Write-Host "[cloak-harness] fingerprint: $Fingerprint (stable for this persona)"

& $Bin @ChromiumArgs
