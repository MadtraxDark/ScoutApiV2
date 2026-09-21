param(
    [string]$Url = "",
    [switch]$Login,
    [switch]$MercadoLivre,
    [switch]$NoProxy,
    [switch]$Humanize
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-DockerQuiet {
    param([Parameter(Mandatory = $true)][string[]]$DockerArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker @DockerArgs 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

Write-Host "Stopping API (avoids Camoufox profile lock)..."
$null = Invoke-DockerQuiet -DockerArgs @("compose", "stop", "api")

$python = $null
if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source }
}
if (-not $python) {
    Write-Error "Python not found. Create .venv: python -m venv .venv && .\.venv\Scripts\pip install -e ."
}

$argList = @("scripts\seed_camoufox_profile.py")
if ($MercadoLivre) {
    $argList += "--mercadolivre"
}
elseif ($Login) {
    $argList += "--login"
}
if ($Url) {
    $argList += @("--url", $Url)
}
if ($NoProxy) {
    $argList += "--no-proxy"
}
if ($Humanize) {
    $argList += "--humanize"
}

Write-Host "Launching headed Camoufox seed..."
if ($MercadoLivre) {
    Write-Host "ML: warm home/lista — sem senha; feche Snoopy se aparecer."
} else {
    Write-Host "Dica: use e-mail/senha da Shopee. Login Google costuma travar."
}
& $python @argList
$exit = $LASTEXITCODE

if ($exit -eq 0) {
    Write-Host ""
    Write-Host "Starting API with bind-mounted profile..."
    $null = Invoke-DockerQuiet -DockerArgs @("compose", "up", "-d", "api")
}

exit $exit
