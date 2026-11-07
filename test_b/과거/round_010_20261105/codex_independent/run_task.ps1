param([ValidateSet('t1','t2')][string]$TaskName)
$ErrorActionPreference = 'Continue'
$taskDirectory = $PSScriptRoot
$scriptName = if ($TaskName -eq 't1') {'t1_decompose.py'} else {'t2_state_audit.py'}
$started = (Get-Date).ToString('o')
$logPath = Join-Path $taskDirectory ($TaskName + '_run_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
& python -B -u (Join-Path $taskDirectory $scriptName) *> $logPath
$processExitCode = $LASTEXITCODE
$receiptPath = Join-Path $taskDirectory ($TaskName + '_execution.json')
& python -B (Join-Path $taskDirectory 'record_execution.py') $TaskName $scriptName $started ((Get-Date).ToString('o')) $processExitCode $logPath
Get-Content -LiteralPath $logPath -Tail 12
Write-Output ('ACTUAL_SCRIPT_EXIT_CODE=' + $processExitCode)
exit $processExitCode
