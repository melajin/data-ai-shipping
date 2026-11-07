$ErrorActionPreference = 'Stop'
$counterPath = Join-Path $PSScriptRoot 'mock_calls.txt'
Add-Content -LiteralPath $counterPath -Value 'mock_call' -Encoding UTF8
ConvertTo-Json -InputObject @($args) | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'mock_arguments.json') -Encoding UTF8
Write-Output '{"ok":true,"result":{"launch":{"outcome":{"kind":"structured","handle":"TEST_ONLY_HANDLE"},"prompt":{"outcome":"journaled"}}}}'
$global:LASTEXITCODE = 0
