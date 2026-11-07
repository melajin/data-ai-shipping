param([ValidateSet('t1','t2')][string]$TaskName)
$ErrorActionPreference = 'Continue'
$taskDirectory = $PSScriptRoot
$scriptName = if ($TaskName -eq 't1') {'t1_decompose.py'} else {'t2_state_audit.py'}
$started = (Get-Date).ToString('o')
$logPath = Join-Path $taskDirectory ($TaskName + '_run_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
& python -B -u (Join-Path $taskDirectory $scriptName) *> $logPath
$processExitCode = $LASTEXITCODE
$receiptPath = Join-Path $taskDirectory ($TaskName + '_execution.json')
$receipts = @()
if (Test-Path -LiteralPath $receiptPath) { $receipts = @(Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json) }
$receipts += [PSCustomObject]@{script=$scriptName;started_at=$started;ended_at=(Get-Date).ToString('o');exit_code=$processExitCode;log_path=$logPath}
ConvertTo-Json -InputObject @($receipts) -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Get-Content -LiteralPath $logPath -Tail 12
Write-Output ('ACTUAL_SCRIPT_EXIT_CODE=' + $processExitCode)
exit $processExitCode
