$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$distOutput = Join-Path $projectRoot "dist\GazetE"
$distRoot = Join-Path $projectRoot "dist"
if (Test-Path $distOutput) {
  $resolvedDistRoot = (Resolve-Path $distRoot).Path
  $resolvedDistOutput = (Resolve-Path $distOutput).Path
  if (-not $resolvedDistOutput.StartsWith($resolvedDistRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove unexpected path: $resolvedDistOutput"
  }
  Remove-Item -LiteralPath $resolvedDistOutput -Recurse -Force
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string] $FilePath,
    [string[]] $Arguments
  )
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
  }
}

Invoke-Checked python @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked python @("-m", "pip", "install", "-e", ".")
Invoke-Checked python @("-m", "pip", "install", "pyinstaller")

$env:PLAYWRIGHT_BROWSERS_PATH = "0"
Invoke-Checked python @("-m", "playwright", "install", "chromium")

$pyinstallerWorkPath = Join-Path $env:TEMP "GazetE-pyinstaller-build"
$pyinstallerSpecPath = Join-Path $projectRoot "build\pyinstaller-spec"
New-Item -ItemType Directory -Force -Path $pyinstallerSpecPath | Out-Null
$templatesData = "$projectRoot\templates;templates"
$staticData = "$projectRoot\static;static"
$dataData = "$projectRoot\data;data"
$schemasData = "$projectRoot\schemas;schemas"

Invoke-Checked python @(
  "-m", "PyInstaller",
  "--clean",
  "--noconfirm",
  "--noconsole",
  "--name", "GazetE",
  "--workpath", $pyinstallerWorkPath,
  "--specpath", $pyinstallerSpecPath,
  "--collect-all", "playwright",
  "--add-data", $templatesData,
  "--add-data", $staticData,
  "--add-data", $dataData,
  "--add-data", $schemasData,
  "chatgpt_haber\one_click.py"
)

Write-Host ""
Write-Host "Hazir: $projectRoot\dist\GazetE\GazetE.exe"
Write-Host "Bu klasoru komple baska bilgisayara kopyalayabilirsiniz."
