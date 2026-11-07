param(
    [Parameter(Mandatory = $true)]
    [string]$Output
)
$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot '../src/run_analysis.py') --output $Output
exit $LASTEXITCODE
