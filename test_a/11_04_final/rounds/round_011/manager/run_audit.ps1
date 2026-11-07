param([Parameter(Mandatory=$true)][ValidateSet('mock_01','mock_02','audit_01')][string]$RunId)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $taskRoot
$roundDir=Join-Path $taskRoot 'rounds/round_011'
$mapPath=Join-Path $roundDir 'review/approved_sources.json'
$approved=Get-Content -LiteralPath $mapPath -Raw -Encoding UTF8|ConvertFrom-Json
function Check-Map {
  $rows=@(foreach($prop in $approved.sha256.PSObject.Properties){
    $actual=(Get-FileHash -LiteralPath (Join-Path $taskRoot $prop.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{path=$prop.Name;expected=$prop.Value.ToLowerInvariant();actual=$actual;match=($actual -eq $prop.Value.ToLowerInvariant())}
  })
  return ,$rows
}
$before=Check-Map
if(@($before|Where-Object {-not $_.match}).Count){throw 'Approval/live hash mismatch before launch'}
if($RunId -eq 'audit_01'){
  $mockPath=Join-Path $roundDir 'logs/mock_01/receipt.json'
  if(Test-Path -LiteralPath (Join-Path $roundDir 'logs/mock_02/receipt.json')){$mockPath=Join-Path $roundDir 'logs/mock_02/receipt.json'}
  $mock=Get-Content -LiteralPath $mockPath -Raw -Encoding UTF8|ConvertFrom-Json
  if(-not $mock.completed -or $mock.approval_sha256 -ne (Get-FileHash -LiteralPath $mapPath).Hash){throw 'No passing exact-map mock'}
}
if($RunId -eq 'mock_02'){
  $first=Get-Content -LiteralPath (Join-Path $roundDir 'logs/mock_01/receipt.json') -Raw -Encoding UTF8|ConvertFrom-Json
  if($first.completed){throw 'Second mock forbidden after successful first mock'}
}
$os=Get-CimInstance Win32_OperatingSystem
$available=$os.FreePhysicalMemory/1MB
if($available -lt 0.5){throw 'Available RAM below 0.5GiB: do alternative work and recheck before this run'}
$logDir=Join-Path $roundDir ('logs/'+$RunId)
New-Item -ItemType Directory -Force -Path $logDir|Out-Null
$claim=[IO.File]::Open((Join-Path $logDir 'execution.claim'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$claim.Dispose()
$sourceDir=Join-Path $logDir 'source'
New-Item -ItemType Directory -Force -Path $sourceDir|Out-Null
$snapshots=@(foreach($name in @('verify_frozen_run.py','test_verify_frozen_run.py','run_audit.ps1')){
  $relative=if($name -eq 'run_audit.ps1'){'rounds/round_011/manager/'+$name}else{'rounds/round_011/code/'+$name}
  $expected=$approved.sha256.$relative
  if(-not $expected){throw "Missing approved code: $relative"}
  $dst=Join-Path $sourceDir $name
  Copy-Item -LiteralPath (Join-Path $taskRoot $relative) -Destination $dst
  $actual=(Get-FileHash -LiteralPath $dst).Hash.ToLowerInvariant()
  if($actual -ne $expected.ToLowerInvariant()){throw 'Copied snapshot differs'}
  [ordered]@{path=$dst;sha256=$actual}
})
$scriptName=if($RunId -like 'mock*'){'test_verify_frozen_run.py'}else{'verify_frozen_run.py'}
$python='C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$snapshotScript=Join-Path $sourceDir $scriptName
$argsList=@('-B','-S',('"'+$snapshotScript+'"'))
if($RunId -eq 'audit_01'){$argsList+=@('--source-round','round_010','--output','rounds/round_011/artifacts/provenance_audit.json')}
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:TMP=Join-Path $roundDir 'logs/tmp'
$env:TEMP=$env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP|Out-Null
$started=[DateTime]::UtcNow.ToString('o')
$watch=[Diagnostics.Stopwatch]::StartNew()
$proc=Start-Process -FilePath $python -ArgumentList $argsList -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'stdout.txt') -RedirectStandardError (Join-Path $logDir 'stderr.txt') -PassThru
$ownedPid=$proc.Id
$creation=$proc.StartTime.ToUniversalTime().ToString('o')
$finished=$proc.WaitForExit(28000)
if(-not $finished){$proc.Kill();$proc.WaitForExit(2000)|Out-Null}
$proc.Refresh()
$exitConfirmed=$proc.HasExited
$exitCode=if($exitConfirmed){$proc.ExitCode}else{$null}
$watch.Stop()
$after=Check-Map
$snapshotAfter=@(foreach($row in $snapshots){[ordered]@{path=$row.path;sha256=(Get-FileHash -LiteralPath $row.path).Hash.ToLowerInvariant();match=((Get-FileHash -LiteralPath $row.path).Hash.ToLowerInvariant() -eq $row.sha256)}})
$completed=$finished -and $exitConfirmed -and $exitCode -eq 0 -and (@($after|Where-Object {-not $_.match}).Count -eq 0) -and (@($snapshotAfter|Where-Object {-not $_.match}).Count -eq 0)
$receipt=[ordered]@{run_id=$RunId;started_utc=$started;finished_utc=[DateTime]::UtcNow.ToString('o');completed=$completed;exit_code=$exitCode;timed_out=(-not $finished);elapsed_seconds=$watch.Elapsed.TotalSeconds;timeout_seconds=30;pid=$ownedPid;creation_utc=$creation;owned_process_exited=$proc.HasExited;command=@($python)+$argsList;available_ram_gib_before=$available;expected_peak_mib=100;expected_peak_basis='stdlib small JSON and 1MiB streaming buffer; no model imports';other_python_processes_after=@(Get-Process python* -ErrorAction SilentlyContinue|Select-Object Id,ProcessName);approval_sha256=(Get-FileHash -LiteralPath $mapPath).Hash;precheck=$before;postcheck=$after;snapshots=$snapshots;snapshot_postcheck=$snapshotAfter;historical_round010_outcome_unchanged=$true;note='This is audit execution completion, not historical model gate success. No process tree created by approved audit code.'}
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $logDir 'receipt.json') -Encoding UTF8
$receipt|Select-Object run_id,completed,exit_code,elapsed_seconds,available_ram_gib_before,owned_process_exited|ConvertTo-Json
if(-not $completed){exit 4}
