# Local smoke test. The Orca command is mocked; no real agent is launched.
$ErrorActionPreference = 'Stop'
$fixtureRoot = Join-Path $PSScriptRoot ('test_artifacts\' + [Guid]::NewGuid().ToString('N'))
$fixtureAutomation = Join-Path $fixtureRoot 'automation'
New-Item -ItemType Directory -Path $fixtureAutomation -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'rounds\round_001') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start-NextSession.ps1') -Destination (Join-Path $fixtureAutomation 'Start-NextSession.ps1')
foreach ($name in @('AGENTS.md', 'CYCLE_PROTOCOL.md', 'NEXT_SESSION.md')) {
    Set-Content -LiteralPath (Join-Path $fixtureRoot $name) -Value 'TEST FIXTURE ONLY - no real experiment' -Encoding UTF8
}
Set-Content -LiteralPath (Join-Path $fixtureRoot 'rounds\round_001\ROUND_REPORT.md') -Value 'TEST FIXTURE ONLY' -Encoding UTF8
$mockPath = Join-Path $fixtureAutomation 'Mock-Orca.ps1'
@'
$ErrorActionPreference = 'Stop'
$counterPath = Join-Path $PSScriptRoot 'mock_calls.txt'
Add-Content -LiteralPath $counterPath -Value 'mock_call' -Encoding UTF8
ConvertTo-Json -InputObject @($args) | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'mock_arguments.json') -Encoding UTF8
Write-Output '{"ok":true,"result":{"launch":{"outcome":{"kind":"structured","handle":"TEST_ONLY_HANDLE"},"prompt":{"outcome":"journaled"}}}}'
$global:LASTEXITCODE = 0
'@ | Set-Content -LiteralPath $mockPath -Encoding UTF8
$previousCli = $env:ORCA_CLI_COMMAND
$env:ORCA_CLI_COMMAND = $mockPath
$launcher = Join-Path $fixtureAutomation 'Start-NextSession.ps1'
$statusPath = Join-Path $fixtureRoot 'STATUS.json'
try {
    '{"current_round":"round_001","handoff":{"ready":false}}' | Set-Content -LiteralPath $statusPath -Encoding UTF8
    $unreadyBlocked = $false
    try { & $launcher -FromRound round_001 | Out-Null } catch { $unreadyBlocked = $_.Exception.Message -like '*handoff.ready=true*' }
    if (-not $unreadyBlocked) { throw 'Expected unready handoff to be blocked.' }
    if (Test-Path -LiteralPath (Join-Path $fixtureAutomation 'mock_calls.txt')) { throw 'Mock was invoked before readiness.' }
    '{"current_round":"round_001","handoff":{"ready":true}}' | Set-Content -LiteralPath $statusPath -Encoding UTF8
    $first = (& $launcher -FromRound round_001 | Out-String) | ConvertFrom-Json
    $second = (& $launcher -FromRound round_001 | Out-String) | ConvertFrom-Json
    $callCount = @(Get-Content -LiteralPath (Join-Path $fixtureAutomation 'mock_calls.txt')).Count
    if (-not $first.accepted -or -not $second.accepted -or $callCount -ne 1) { throw 'Expected one accepted mock launch and idempotent duplicate receipt.' }
    $mockArguments = Get-Content -LiteralPath (Join-Path $fixtureAutomation 'mock_arguments.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $promptIndex = [Array]::IndexOf($mockArguments, '--prompt')
    $unicodeLead = -join ([char[]]@(0xC0AC, 0xC6A9, 0xC790, 0xAC00))
    $rawNameLead = -join ([char[]]@(0xBB38, 0xC81C))
    $unicodePromptPassed = $promptIndex -ge 0 -and $mockArguments[$promptIndex + 1].StartsWith($unicodeLead) -and $mockArguments[$promptIndex + 1].Contains("F:\$rawNameLead")
    if (-not $unicodePromptPassed) { throw "Korean prompt/raw path corrupted before CLI invocation. Inspect $fixtureAutomation\mock_arguments.json" }
    [ordered]@{
        kind = 'mock_smoke_test_no_real_agents'; completed_at_utc = [DateTime]::UtcNow.ToString('o')
        readiness_guard_passed = $unreadyBlocked; successful_receipt_parsed = $first.accepted
        duplicate_submission_guard_passed = ($callCount -eq 1); mock_call_count = $callCount
        unicode_prompt_and_raw_path_passed = $unicodePromptPassed
        fixture_directory = $fixtureRoot; real_sessions_started = 0
    } | ConvertTo-Json -Depth 5 | Tee-Object -FilePath (Join-Path $PSScriptRoot 'launcher_smoke_result.json')
} finally {
    $env:ORCA_CLI_COMMAND = $previousCli
}
