param(
    [string]$EnvName = "kindle_app"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    $Program = $Command[0]
    $Arguments = @()
    if ($Command.Count -gt 1) {
        $Arguments = $Command[1..($Command.Count - 1)]
    }
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program $($Arguments -join ' ')"
    }
}

function Invoke-CondaRun {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    Invoke-Checked (@("conda", "run", "-n", $EnvName) + $Command)
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "conda was not found in PATH. Install Miniconda/Anaconda first."
}

$escapedEnvName = [regex]::Escape($EnvName)
$envExists = [bool](
    conda env list |
        Select-String -Pattern "^\s*$escapedEnvName\s+(?:\*\s+)?"
)

if ($envExists) {
    Invoke-Checked @("conda", "env", "update", "-n", $EnvName, "-f", "environment.yml", "--prune")
} else {
    Invoke-Checked @("conda", "env", "create", "-n", $EnvName, "-f", "environment.yml")
}

Invoke-CondaRun @("python", "-m", "pip", "install", "--force-reinstall", "--no-deps", "-e", ".")
Invoke-CondaRun @("python", "-c", "import kindle_vocab_app; print('kindle_vocab_app import ok:', kindle_vocab_app.__file__)")
Invoke-CondaRun @("npm", "install")
Invoke-CondaRun @("npm", "rebuild", "esbuild")
Invoke-CondaRun @("python", "-c", "import nltk; [nltk.download(package, quiet=True) for package in ('wordnet', 'omw-1.4', 'averaged_perceptron_tagger_eng', 'punkt_tab')]")
Invoke-CondaRun @("kindle-vocab-doctor")

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run:"
Write-Host "  conda activate $EnvName"
Write-Host "  kindle-vocab-app"
