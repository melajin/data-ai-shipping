param([ValidateSet('smoke','mock','audit')][string]$Mode)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $taskRoot
if([datetime]::UtcNow -ge [datetime]'2026-11-04T23:13:35Z'){throw 'Too late to start a bounded mode before execution cutoff'}
$rd=Join-Path $taskRoot 'rounds/round_019'
$mapPath=Join-Path $rd 'review/approved_sources.json'
$map=Get-Content -Raw -Encoding UTF8 $mapPath | ConvertFrom-Json
$mapHash=(Get-FileHash -LiteralPath $mapPath).Hash.ToLowerInvariant()
if($map.schema -ne 'round019_approved_sources.v1'){throw 'Wrong approval schema'}
$manifest=Join-Path $rd 'code/candidate_sources.json'
$ack=Join-Path $rd 'code/author_freeze_ack.json'
if((Get-FileHash $manifest).Hash.ToLowerInvariant() -ne $map.candidate_manifest_sha256){throw 'Manifest hash mismatch'}
if((Get-FileHash $ack).Hash.ToLowerInvariant() -ne $map.candidate_freeze_ack_sha256){throw 'ACK hash mismatch'}
foreach($entry in $map.sha256.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $taskRoot $entry.Name)).Hash.ToLowerInvariant() -ne $entry.Value){throw 'Approved live source mismatch'}}
$previous=if($Mode -eq 'mock'){@('smoke')}elseif($Mode -eq 'audit'){@('smoke','mock')}else{@()}
foreach($prev in $previous){
  $receipt=Get-Content -Raw -Encoding UTF8 (Join-Path $rd "logs/${prev}_01/receipt.json") | ConvertFrom-Json
  $wrapper=Get-Content -Raw -Encoding UTF8 (Join-Path $rd "logs/${prev}_01/wrapper_receipt.json") | ConvertFrom-Json
  $outer=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "${prev}_launch.json") | ConvertFrom-Json
  if(-not $receipt.completed -or $wrapper.state -ne 'completed' -or $outer.exit_code -ne 0 -or -not $outer.within_outer_wall_budget -or $receipt.approved_map_sha256 -ne $mapHash -or $wrapper.approved_map_sha256 -ne $mapHash){throw "Previous full wrapper did not pass: $prev"}
}
$os=Get-CimInstance Win32_OperatingSystem
$free=$os.FreePhysicalMemory/1MB
$other=@(Get-Process python,pythonw -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime,WorkingSet64)
$resource=@{utc=[datetime]::UtcNow.ToString('o');mode=$Mode;available_gib=$free;expected_peak_mib=200;estimate_basis='Sequential small stdlib JSON and opaque streaming hashes; no model';other_python=$other;approved_map_sha256=$mapHash}
$resource | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot "${Mode}_preflight.json")
if($free -lt 0.5 -or $other.Count -gt 0){throw 'Resource gate; defer without starting child'}
foreach($dir in @('tmp','cache')){New-Item -ItemType Directory -Force -Path (Join-Path $rd $dir) | Out-Null}
$env:TEMP=Join-Path $rd 'tmp';$env:TMP=$env:TEMP;$env:PYTHONPYCACHEPREFIX=Join-Path $rd 'cache';$env:PYTHONDONTWRITEBYTECODE='1'
$claim=Join-Path $PSScriptRoot "${Mode}_launch.claim"
$fs=[IO.File]::Open($claim,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$fs.Dispose()
$scriptPath=Join-Path $rd 'code/run_saved_m4_audit.ps1'
$argsList=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$scriptPath+'"'),'-Mode',$Mode)
$started=[datetime]::UtcNow.ToString('o');$clock=[Diagnostics.Stopwatch]::StartNew()
$p=Start-Process -FilePath "$env:WINDIR/System32/WindowsPowerShell/v1.0/powershell.exe" -ArgumentList $argsList -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot "${Mode}_stdout.txt") -RedirectStandardError (Join-Path $PSScriptRoot "${Mode}_stderr.txt")
$elapsed=$clock.Elapsed.TotalSeconds
$limit=if($Mode -eq 'smoke'){15}else{30}
$result=@{mode=$Mode;pid=$p.Id;started_utc=$started;finished_utc=[datetime]::UtcNow.ToString('o');argv=$argsList;exit_code=$p.ExitCode;outer_wall_seconds=$elapsed;outer_wall_budget_seconds=$limit;within_outer_wall_budget=($elapsed -le $limit);approved_map_sha256=$mapHash;map_stable=((Get-FileHash $mapPath).Hash.ToLowerInvariant() -eq $mapHash)}
$result | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot "${Mode}_launch.json")
$result | ConvertTo-Json -Depth 6
