param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('smoke','mock','audit')]
  [string]$Mode
)

$ErrorActionPreference = 'Stop'
$python = 'C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$roundDir = Split-Path -Parent $PSScriptRoot
$taskRoot = Split-Path -Parent (Split-Path -Parent $roundDir)
$auditor = Join-Path $PSScriptRoot 'saved_m4_audit.py'
$relativeSources = @('rounds/round_016/code/saved_m4_audit.py','rounds/round_016/code/run_saved_m4_audit.ps1')

function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Get-FreeRamGiB {
  $os = Get-CimInstance -ClassName Win32_OperatingSystem
  [double]$os.FreePhysicalMemory / 1MB
}
function Get-PythonInventory {
  @(Get-Process -Name 'python','pythonw' -ErrorAction SilentlyContinue | ForEach-Object {
    [ordered]@{ pid=[int]$_.Id; name=$_.ProcessName; creation_utc=$_.StartTime.ToUniversalTime().ToString('o') }
  })
}
function ConvertTo-Arg([string]$Value) {
  if ($Value.Contains([char]34)) { throw 'Unexpected quote in fixed auditor argument' }
  [string][char]34 + $Value + [string][char]34
}
function Get-TreeRows([int]$RootPid) {
  $all = @(Get-CimInstance -ClassName Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CreationDate,WorkingSetSize)
  $owned = [System.Collections.Generic.HashSet[int]]::new(); [void]$owned.Add($RootPid)
  $changed=$true
  while ($changed) {
    $changed=$false
    foreach ($row in $all) {
      if ($owned.Contains([int]$row.ParentProcessId) -and -not $owned.Contains([int]$row.ProcessId)) {
        [void]$owned.Add([int]$row.ProcessId); $changed=$true
      }
    }
  }
  @(
    foreach ($pidValue in $owned) {
      $row = $all | Where-Object { [int]$_.ProcessId -eq $pidValue } | Select-Object -First 1
      if ($row) {
        $created=$null
        try { $created=[System.Management.ManagementDateTimeConverter]::ToDateTime([string]$row.CreationDate).ToUniversalTime().ToString('o') } catch { }
        [ordered]@{pid=$pidValue; parent_pid=[int]$row.ParentProcessId; name=[string]$row.Name; creation_utc=$created; working_set_bytes=[long]$row.WorkingSetSize; root=($pidValue -eq $RootPid)}
      }
    }
  )
}
function Get-OwnedResiduals($Seen) {
  $residual=@()
  foreach ($entry in $Seen.Values) {
    try {
      $current=Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $([int]$entry.pid)"
      if ($current) {
        $created=[System.Management.ManagementDateTimeConverter]::ToDateTime([string]$current.CreationDate).ToUniversalTime().ToString('o')
        if ($created -eq $entry.creation_utc) { $residual += [ordered]@{pid=$entry.pid; reason='same_owned_process_still_present'} }
      }
    } catch { $residual += [ordered]@{pid=$entry.pid; reason='identity_check_failed'; error=$_.Exception.Message} }
  }
  $residual
}
function Invoke-Probe([string]$Label,[string]$Code,[int]$Expected,[int]$WaitMs,[int]$CleanupMs) {
  $ramBefore=Get-FreeRamGiB; $pythonBefore=Get-PythonInventory
  if ($ramBefore -lt 0.5) { throw "RAM precheck below 0.5 GiB before $Label" }
  if ($pythonBefore.Count -gt 0) { throw "Concurrent Python process found before $Label; probe not started" }
  $psi=[System.Diagnostics.ProcessStartInfo]::new(); $psi.FileName=$python; $psi.WorkingDirectory=$taskRoot
  $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
  $args=@('-B','-S','-c',$Code); $psi.Arguments=(($args | ForEach-Object { ConvertTo-Arg ([string]$_) }) -join ' ')
  $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1'; $psi.EnvironmentVariables['PYTHONUTF8']='1'; $psi.EnvironmentVariables['PYTHONNOUSERSITE']='1'
  [void]$psi.EnvironmentVariables.Remove('PYTHONPATH'); [void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new(); $p.StartInfo=$psi; $clock=[System.Diagnostics.Stopwatch]::StartNew()
  $startedUtc=[DateTime]::UtcNow.ToString('o'); $started=$p.Start(); if (-not $started) { throw "Process.Start returned false for $Label" }
  $pidValue=[int]$p.Id; $creation=$p.StartTime.ToUniversalTime().ToString('o')
  $stdoutTask=$p.StandardOutput.ReadToEndAsync(); $stderrTask=$p.StandardError.ReadToEndAsync()
  $seen=@{}; $seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $deadline=[DateTime]::UtcNow.AddMilliseconds($WaitMs); $deadlineReached=$false; $memoryStop=$false; $killAttempted=$false
  $waitReturned=$false; $exitObservedBeforeCleanup=$false; $minRam=$ramBefore; $samples=@(); $errorText=$null
  while (-not $p.HasExited -and [DateTime]::UtcNow -lt $deadline) {
    $available=Get-FreeRamGiB; if ($available -lt $minRam) { $minRam=$available }
    $tree=@(Get-TreeRows -RootPid $pidValue); $treeBytes=[long]0
    foreach ($row in $tree) { $seen[[string]$row.pid]=$row; if ($row.working_set_bytes) { $treeBytes += [long]$row.working_set_bytes } }
    $samples += [ordered]@{elapsed_seconds=[math]::Round($clock.Elapsed.TotalSeconds,3);available_ram_gib=[math]::Round($available,4);owned_tree_working_set_bytes=$treeBytes;owned_pids=@($tree | ForEach-Object { [int]$_.pid })}
    if ($available -lt 0.5) { $memoryStop=$true; $killAttempted=$true; try { $p.Kill() } catch { $errorText=$_.Exception.Message }; break }
    $remaining=[math]::Max(1,[int]($deadline-[DateTime]::UtcNow).TotalMilliseconds)
    $waitReturned=[bool]$p.WaitForExit([math]::Min(200,$remaining))
    if (-not $waitReturned -and $p.HasExited) { $waitReturned=$true; break }
  }
  if ($p.HasExited) { $exitObservedBeforeCleanup=$true }
  elseif ([DateTime]::UtcNow -ge $deadline) { $deadlineReached=$true; $killAttempted=$true; try { $p.Kill() } catch { $errorText=$_.Exception.Message } }
  $cleanupClock=[System.Diagnostics.Stopwatch]::StartNew()
  while (-not $p.HasExited -and $cleanupClock.ElapsedMilliseconds -lt $CleanupMs) { [void]$p.WaitForExit([math]::Min(100,[math]::Max(1,$CleanupMs-[int]$cleanupClock.ElapsedMilliseconds))) }
  $exitConfirmed=[bool]$p.HasExited; $exitCode=$null
  if ($exitConfirmed) { try { $exitCode=[int]$p.ExitCode } catch { $exitConfirmed=$false } }
  $drained=$false; $stdout=''; $stderr=''
  if ($exitConfirmed) {
    try {
      $remainingDrain=[math]::Max(1,1000-[int]$cleanupClock.ElapsedMilliseconds)
      $tasks=@($stdoutTask,$stderrTask)
      $drained=[bool][System.Threading.Tasks.Task]::WaitAll($tasks,$remainingDrain)
      if ($drained) { $stdout=[string]$stdoutTask.Result; $stderr=[string]$stderrTask.Result }
    } catch { $errorText=$_.Exception.Message }
  }
  foreach ($row in @(Get-TreeRows -RootPid $pidValue)) { $seen[[string]$row.pid]=$row }
  $residuals=@(Get-OwnedResiduals -Seen $seen); $treeClear=$residuals.Count -eq 0
  $timedOut=[bool]($deadlineReached -and -not $exitObservedBeforeCleanup -and -not $memoryStop)
  $expectedMatches=($exitConfirmed -and ($exitCode -is [int]) -and $exitCode -eq $Expected)
  $classification=if ($memoryStop) {'memory_stop'} elseif ($timedOut) {'deadline_timeout'} elseif ($exitConfirmed -and $exitCode -eq 0) {'completed'} elseif ($exitConfirmed) {'nonzero_exit'} else {'incomplete'}
  $markerOut=if ($Label -eq 'immediate_exit_0') {'probe0-out'} elseif ($Label -eq 'immediate_exit_7') {'probe7-out'} elseif ($Label -eq 'monitored_success') {'probe-sleep-out'} else {$null}
  $markerErr=if ($Label -eq 'immediate_exit_0') {'probe0-err'} elseif ($Label -eq 'immediate_exit_7') {'probe7-err'} elseif ($Label -eq 'monitored_success') {'probe-sleep-err'} else {$null}
  $markers=if ($markerOut) { $stdout.Contains($markerOut) -and $stderr.Contains($markerErr) } else {$true}
  $completed=[bool]($expectedMatches -and -not $timedOut -and -not $memoryStop -and $drained -and $treeClear -and $markers -and (($Label -eq 'immediate_exit_7') -or $classification -eq 'completed'))
  $record=[ordered]@{label=$Label;command=@($python)+$args;pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');expected_exit_code=$Expected;exit_code=$exitCode;exit_confirmed=$exitConfirmed;wait_returned=$waitReturned;has_exited_after_wait=$exitConfirmed;actual_wait_deadline_reached=$deadlineReached;exit_observed_before_cleanup=$exitObservedBeforeCleanup;timed_out=$timedOut;memory_stop=$memoryStop;kill_attempted=$killAttempted;classification=$classification;elapsed_seconds=$clock.Elapsed.TotalSeconds;wait_timeout_seconds=$WaitMs/1000.0;cleanup_timeout_seconds=$CleanupMs/1000.0;cleanup_elapsed_seconds=$cleanupClock.Elapsed.TotalSeconds;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;stdout_marker_present=if($markerOut){$stdout.Contains($markerOut)}else{$null};stderr_marker_present=if($markerErr){$stderr.Contains($markerErr)}else{$null};completed=$completed;error=$errorText}
  $p.Dispose(); $record
}
function Invoke-Auditor([string]$RunMode,[int]$WaitMs) {
  $ramBefore=Get-FreeRamGiB; $pythonBefore=Get-PythonInventory
  if($ramBefore -lt 0.5){throw "Auditor RAM precheck below 0.5 GiB for $RunMode"}
  if($pythonBefore.Count -gt 0){throw "Concurrent Python process found before auditor $RunMode"}
  $psi=[System.Diagnostics.ProcessStartInfo]::new(); $psi.FileName=$python; $psi.WorkingDirectory=$taskRoot
  $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
  $args=@('-B','-S',$auditor,'--root',$taskRoot,'--mode',$RunMode); $psi.Arguments=(($args | ForEach-Object { ConvertTo-Arg ([string]$_) }) -join ' ')
  $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1'; $psi.EnvironmentVariables['PYTHONUTF8']='1'; $psi.EnvironmentVariables['PYTHONNOUSERSITE']='1'
  [void]$psi.EnvironmentVariables.Remove('PYTHONPATH'); [void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new(); $p.StartInfo=$psi; $clock=[System.Diagnostics.Stopwatch]::StartNew()
  $startedUtc=[DateTime]::UtcNow.ToString('o'); $started=$p.Start(); if(-not $started){throw 'auditor Process.Start returned false'}
  $pidValue=[int]$p.Id; $creation=$p.StartTime.ToUniversalTime().ToString('o'); $outTask=$p.StandardOutput.ReadToEndAsync(); $errTask=$p.StandardError.ReadToEndAsync()
  $seen=@{};$seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $samples=@();$minRam=$ramBefore
  $deadline=[DateTime]::UtcNow.AddMilliseconds($WaitMs); $deadlineReached=$false; $waitReturned=$false
  while(-not $p.HasExited -and [DateTime]::UtcNow -lt $deadline){
    $available=Get-FreeRamGiB;if($available -lt $minRam){$minRam=$available}
    $tree=@(Get-TreeRows -RootPid $pidValue);foreach($row in $tree){$seen[[string]$row.pid]=$row}
    $samples+= [ordered]@{elapsed_seconds=[math]::Round($clock.Elapsed.TotalSeconds,3);available_ram_gib=[math]::Round($available,4);owned_pids=@($tree|ForEach-Object{[int]$_.pid})}
    $remaining=[math]::Max(1,[int]($deadline-[DateTime]::UtcNow).TotalMilliseconds);$waitReturned=[bool]$p.WaitForExit([math]::Min(250,$remaining));if(-not $waitReturned -and $p.HasExited){$waitReturned=$true;break}
  }
  if($p.HasExited){$waitReturned=$true}else{$deadlineReached=([DateTime]::UtcNow -ge $deadline)}
  $killAttempted=$false;if($deadlineReached -and -not $p.HasExited){$killAttempted=$true;try{$p.Kill()}catch{}}
  $cleanup=[System.Diagnostics.Stopwatch]::StartNew();while(-not $p.HasExited -and $cleanup.ElapsedMilliseconds -lt 1000){[void]$p.WaitForExit([math]::Min(100,[math]::Max(1,1000-[int]$cleanup.ElapsedMilliseconds)))}
  $exitConfirmed=[bool]$p.HasExited;$exitCode=$null;if($exitConfirmed){try{$exitCode=[int]$p.ExitCode}catch{$exitConfirmed=$false}}
  $drained=$false;$stdout='';$stderr='';if($exitConfirmed){try{$drained=[bool][System.Threading.Tasks.Task]::WaitAll(@($outTask,$errTask),1000);if($drained){$stdout=[string]$outTask.Result;$stderr=[string]$errTask.Result}}catch{}}
  foreach($row in @(Get-TreeRows -RootPid $pidValue)){$seen[[string]$row.pid]=$row};$residuals=@(Get-OwnedResiduals -Seen $seen);$treeClear=$residuals.Count -eq 0
  $record=[ordered]@{pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');command=@($python)+$args;wait_timeout_seconds=$WaitMs/1000.0;actual_wait_deadline_reached=$deadlineReached;wait_returned=$waitReturned;kill_attempted=$killAttempted;exit_confirmed=$exitConfirmed;exit_code=$exitCode;stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;elapsed_seconds=$clock.Elapsed.TotalSeconds;completed=($exitConfirmed -and $exitCode -eq 0 -and $drained -and $treeClear -and -not $deadlineReached)}
  $p.Dispose();$record
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Required base Python executable is missing' }
if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) { throw 'Saved M4 auditor source is missing' }
Set-Location -LiteralPath $taskRoot
$mapPath=Join-Path $roundDir 'review/approved_sources.json'; if(-not(Test-Path -LiteralPath $mapPath -PathType Leaf)){throw 'Independent approved source map missing'}
$mapHashBefore=Get-Sha256 $mapPath; $approved=Get-Content -Raw -Encoding UTF8 $mapPath | ConvertFrom-Json
if($approved.schema -ne 'round016_approved_sources.v1' -or $approved.round -ne 'round_016'){throw 'Approved source map schema/round mismatch'}
$manifestPath=Join-Path $PSScriptRoot 'candidate_sources.json';$ackPath=Join-Path $PSScriptRoot 'author_freeze_ack.json'
$manifestHashBefore=Get-Sha256 $manifestPath;$ackHashBefore=Get-Sha256 $ackPath
$sourceHashesBefore=@{};foreach($relative in $relativeSources){$path=Join-Path $taskRoot ($relative.Replace('/','\'));$prop=$approved.sha256.PSObject.Properties[$relative];if(-not $prop){throw "Approved map missing $relative"};$actual=Get-Sha256 $path;if($actual -ne ([string]$prop.Value).ToLowerInvariant()){throw "Approved source mismatch: $relative"};$sourceHashesBefore[$relative]=$actual}
$availableBefore=Get-FreeRamGiB;$pythonBefore=Get-PythonInventory
$runId=switch($Mode){'smoke'{'smoke_01'}'mock'{'mock_01'}'audit'{'audit_01'}}
$runDir=Join-Path $roundDir ("logs/"+$runId);New-Item -ItemType Directory -Force -Path $runDir | Out-Null
if((Test-Path -LiteralPath (Join-Path $runDir 'execution.claim')) -or (Test-Path -LiteralPath (Join-Path $runDir 'receipt.json'))){throw "Duplicate execution forbidden for $runId"}
if($Mode -eq 'smoke'){
  if($availableBefore -lt 0.5){throw 'Smoke batch RAM start gate below 0.5 GiB'}
  $batchStartedUtc=[DateTime]::UtcNow.ToString('o');$batchClock=[System.Diagnostics.Stopwatch]::StartNew();$probes=@()
  $probes+=Invoke-Probe 'immediate_exit_0' "import sys; print('probe0-out'); print('probe0-err', file=sys.stderr); raise SystemExit(0)" 0 2500 1000
  $probes+=Invoke-Probe 'immediate_exit_7' "import sys; print('probe7-out'); print('probe7-err', file=sys.stderr); raise SystemExit(7)" 7 2500 1000
  $probes+=Invoke-Probe 'monitored_success' "import sys,time; time.sleep(1.2); print('probe-sleep-out'); print('probe-sleep-err', file=sys.stderr); raise SystemExit(0)" 0 5000 1000
  $probes+=Invoke-Probe 'deadline_timeout' 'import time; time.sleep(5.0)' 0 500 1000
  $completed=[bool]($probes.Count -eq 4 -and $batchClock.Elapsed.TotalSeconds -le 15 -and @($probes[0..2] | Where-Object { -not $_.completed }).Count -eq 0 -and $probes[3].timed_out -and $probes[3].exit_confirmed -and $probes[3].stdout_stderr_drained -and $probes[3].owned_tree_clear)
  $probeReceipt=[ordered]@{schema='round016_process_probe_batch.v1';completed=$completed;started_utc=$batchStartedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');elapsed_seconds=$batchClock.Elapsed.TotalSeconds;timeout_seconds=15;available_ram_gib_before=$availableBefore;other_python_processes_before=$pythonBefore;probes=$probes;wait_false_alone_created_timeout=$false}
  $json=ConvertTo-Json -InputObject $probeReceipt -Depth 20;$enc=[System.Text.UTF8Encoding]::new($false);[System.IO.File]::WriteAllText((Join-Path $runDir 'probe_receipt.json'),$json+"`n",$enc)
  if(-not $completed){throw 'Process-control probe batch failed; receipt preserved'}
}
$waitMs=if($Mode -eq 'smoke'){12000}else{25000};$auditorRecord=Invoke-Auditor -RunMode $Mode -WaitMs $waitMs
$manifestHashAfter=Get-Sha256 $manifestPath;$ackHashAfter=Get-Sha256 $ackPath;$mapHashAfter=Get-Sha256 $mapPath
$sourceHashesAfter=@{};foreach($relative in $relativeSources){$path=Join-Path $taskRoot ($relative.Replace('/','\'));$sourceHashesAfter[$relative]=Get-Sha256 $path}
$sourceStable=($manifestHashBefore -eq $manifestHashAfter -and $ackHashBefore -eq $ackHashAfter -and $mapHashBefore -eq $mapHashAfter)
foreach($relative in $relativeSources){if($sourceHashesBefore[$relative] -ne $sourceHashesAfter[$relative]){$sourceStable=$false}}
$auditorRecord['post_hashes_stable']=$sourceStable;$auditorRecord['approved_map_sha256_before']=$mapHashBefore;$auditorRecord['approved_map_sha256_after']=$mapHashAfter
$auditorRecord['candidate_manifest_sha256_before']=$manifestHashBefore;$auditorRecord['candidate_manifest_sha256_after']=$manifestHashAfter;$auditorRecord['author_ack_sha256_before']=$ackHashBefore;$auditorRecord['author_ack_sha256_after']=$ackHashAfter
$procPath=Join-Path $runDir 'auditor_process.json';[System.IO.File]::WriteAllText($procPath,(ConvertTo-Json -InputObject $auditorRecord -Depth 12)+"`n",[System.Text.UTF8Encoding]::new($false))
$receiptPath=Join-Path $runDir 'receipt.json'
if(Test-Path -LiteralPath $receiptPath){$modeReceipt=Get-Content -Raw -Encoding UTF8 $receiptPath | ConvertFrom-Json;$modeReceipt | Add-Member -NotePropertyName wrapper_process -NotePropertyValue $auditorRecord -Force;$modeReceipt | Add-Member -NotePropertyName approved_map_sha256_after -NotePropertyValue $mapHashAfter -Force;$modeReceipt | Add-Member -NotePropertyName source_hashes_after -NotePropertyValue $sourceHashesAfter -Force;if(-not $sourceStable -or -not $auditorRecord.completed){$modeReceipt.completed=$false};[System.IO.File]::WriteAllText($receiptPath,(ConvertTo-Json -InputObject $modeReceipt -Depth 20)+"`n",[System.Text.UTF8Encoding]::new($false))}
if($auditorRecord.stdout){[Console]::Out.Write($auditorRecord.stdout)};if($auditorRecord.stderr){[Console]::Error.Write($auditorRecord.stderr)}
if(-not $auditorRecord.completed -or -not $sourceStable){exit 4}
exit $auditorRecord.exit_code
