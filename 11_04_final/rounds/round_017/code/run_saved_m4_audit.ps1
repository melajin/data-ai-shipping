param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('smoke','mock','audit')]
  [string]$Mode
)

$ErrorActionPreference = 'Stop'
$script:ModeBudgetMs=if($Mode -eq 'smoke'){15000}else{30000};$script:ModeClock=[System.Diagnostics.Stopwatch]::StartNew();$script:ModeStartedUtc=[DateTime]::UtcNow.ToString('o')
$python = 'C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$roundDir = Split-Path -Parent $PSScriptRoot
$taskRoot = Split-Path -Parent (Split-Path -Parent $roundDir)
$auditor = Join-Path $PSScriptRoot 'saved_m4_audit.py'
$relativeSources = @('rounds/round_017/code/saved_m4_audit.py','rounds/round_017/code/run_saved_m4_audit.ps1')

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
function Convert-CimCreationUtc($Value) {
  if ($null -eq $Value) { throw 'CIM CreationDate is null' }
  if ($Value -is [datetime]) { return $Value.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }
  if ($Value -is [string]) {
    if ([string]::IsNullOrWhiteSpace($Value)) { throw 'CIM CreationDate DMTF string is empty' }
    return [System.Management.ManagementDateTimeConverter]::ToDateTime($Value).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  }
  throw "Unsupported CIM CreationDate type: $($Value.GetType().FullName)"
}
function Get-ProcessClassification([bool]$DeadlineReached,[bool]$MemoryStop,[bool]$ExitObserved,[object]$ExitObservedElapsedSeconds,[bool]$WaitReturned,[object]$WaitReturnedElapsedSeconds,[double]$DeadlineSeconds,[bool]$ExitCodeKnown,[int]$ExitCode) {
  if ($MemoryStop) { return 'memory_stop' }
  if (-not $ExitObserved) { if ($DeadlineReached) { return 'deadline_timeout' }; return 'incomplete' }
  if ($null -eq $ExitObservedElapsedSeconds) { return 'indeterminate' }
  if ([double]$ExitObservedElapsedSeconds -lt $DeadlineSeconds) { if ($ExitCodeKnown -and $ExitCode -eq 0) { return 'completed' }; if ($ExitCodeKnown) { return 'nonzero_exit' }; return 'indeterminate' }
  if ([double]$ExitObservedElapsedSeconds -gt $DeadlineSeconds -and $DeadlineReached -and -not $WaitReturned -and $null -ne $WaitReturnedElapsedSeconds -and [double]$WaitReturnedElapsedSeconds -ge $DeadlineSeconds) { return 'deadline_timeout' }
  return 'indeterminate'
}
function ConvertTo-Arg([string]$Value) {
  if ($Value.Contains([char]34)) { throw 'Unexpected quote in fixed auditor argument' }
  [string][char]34 + $Value + [string][char]34
}
function Get-TreeRows([int]$RootPid,[string]$RootCreationUtc) {
  $all = @(Get-CimInstance -ClassName Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CreationDate,WorkingSetSize)
  $rootRow=$all | Where-Object { [int]$_.ProcessId -eq $RootPid } | Select-Object -First 1
  if($rootRow -and (Convert-CimCreationUtc $rootRow.CreationDate) -ne $RootCreationUtc){throw 'Root PID creation identity mismatch during tree scan'}
  $owned=@{};$owned[[string]$RootPid]=$RootCreationUtc
  $changed=$true
  while ($changed) {
    $changed=$false
    foreach ($row in $all) {
      $parentKey=[string][int]$row.ParentProcessId;$childKey=[string][int]$row.ProcessId
      if ($owned.ContainsKey($parentKey) -and -not $owned.ContainsKey($childKey)) {
        $parentRow=$all | Where-Object { [int]$_.ProcessId -eq [int]$row.ParentProcessId } | Select-Object -First 1
        if(-not $parentRow){throw 'Owned descendant parent identity is unavailable during tree scan'}
        if((Convert-CimCreationUtc $parentRow.CreationDate) -ne $owned[$parentKey]){throw 'Owned descendant parent PID creation identity mismatch'}
        $owned[$childKey]=Convert-CimCreationUtc $row.CreationDate;$changed=$true
      }
    }
  }
  @(
    foreach ($pidText in $owned.Keys) {
      $pidValue=[int]$pidText
      $row = $all | Where-Object { [int]$_.ProcessId -eq $pidValue } | Select-Object -First 1
      if ($row -and (Convert-CimCreationUtc $row.CreationDate) -eq $owned[$pidText]) {
        $created=$owned[$pidText]
        [ordered]@{pid=$pidValue; parent_pid=[int]$row.ParentProcessId; name=[string]$row.Name; creation_utc=$created; working_set_bytes=[long]$row.WorkingSetSize; root=($pidValue -eq $RootPid)}
      }
    }
  )
}
function Get-ModeRemainingMs { [math]::Max(0,$script:ModeBudgetMs-[int]$script:ModeClock.ElapsedMilliseconds) }
function Save-WrapperReceipt([string]$State,[string]$ErrorText) {
  $elapsed=if($script:ModeClock){$script:ModeClock.Elapsed.TotalSeconds}else{$null}
  $body=[ordered]@{schema='round017_wrapper_receipt.v1';mode=$Mode;run_id=$runId;state=$State;claimed=true;approved_map_sha256=$mapHashBefore;source_hashes=$sourceHashesBefore;started_utc=$script:ModeStartedUtc;elapsed_seconds=$elapsed;mode_budget_seconds=if($Mode -eq 'smoke'){15}else{30};probe_records=@($script:ProbeRows);auditor_process=$script:AuditorRecord;error=$ErrorText}
  [System.IO.File]::WriteAllText($script:WrapperReceiptPath,(ConvertTo-Json -InputObject $body -Depth 16)+"`n",[System.Text.UTF8Encoding]::new($false))
}
function Get-OwnedResiduals($Seen) {
  $residual=@()
  foreach ($entry in $Seen.Values) {
    try {
      $current=Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $([int]$entry.pid)"
      if ($current) {
        $created=Convert-CimCreationUtc $current.CreationDate
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
  $modeReserve=if($Mode -eq 'smoke'){4000}else{1500};$modeRemaining=Get-ModeRemainingMs
  if($modeRemaining -le ($CleanupMs+$modeReserve)){throw "Insufficient wrapper-mode budget to start $Label"}
  $WaitMs=[math]::Min($WaitMs,$modeRemaining-$CleanupMs-$modeReserve)
  $psi=[System.Diagnostics.ProcessStartInfo]::new(); $psi.FileName=$python; $psi.WorkingDirectory=$taskRoot
  $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
  $args=@('-B','-S','-c',$Code); $psi.Arguments=(($args | ForEach-Object { ConvertTo-Arg ([string]$_) }) -join ' ')
  $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1'; $psi.EnvironmentVariables['PYTHONUTF8']='1'; $psi.EnvironmentVariables['PYTHONNOUSERSITE']='1'
  [void]$psi.EnvironmentVariables.Remove('PYTHONPATH'); [void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new(); $p.StartInfo=$psi; $clock=[System.Diagnostics.Stopwatch]::StartNew()
  $startedUtc=[DateTime]::UtcNow.ToString('o'); $started=$p.Start(); if (-not $started) { throw "Process.Start returned false for $Label" }
  $pidValue=[int]$p.Id; $creation=$p.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  $stdoutTask=$p.StandardOutput.ReadToEndAsync(); $stderrTask=$p.StandardError.ReadToEndAsync()
  $seen=@{}; $seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $deadlineSeconds=$WaitMs/1000.0; $deadlineReached=$false; $deadlineObservedElapsed=$null; $memoryStop=$false; $killAttempted=$false
  $waitReturned=$false; $waitReturnedElapsed=$null; $exitObserved=$false; $exitObservedElapsed=$null; $exitObservedBeforeCleanup=$false; $minRam=$ramBefore; $samples=@(); $errorText=$null
  while ($true) {
    if ($p.HasExited) { $exitObserved=$true; $exitObservedElapsed=$clock.Elapsed.TotalSeconds; if($exitObservedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$exitObservedElapsed}; break }
    $remaining=[int]($WaitMs-$clock.ElapsedMilliseconds)
    if ($remaining -le 0) { $deadlineReached=$true; $deadlineObservedElapsed=$clock.Elapsed.TotalSeconds; break }
    $available=Get-FreeRamGiB; if ($available -lt $minRam) { $minRam=$available }
    $tree=@(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation); $treeBytes=[long]0
    foreach ($row in $tree) { $seen[[string]$row.pid]=$row; if ($row.working_set_bytes) { $treeBytes += [long]$row.working_set_bytes } }
    $samples += [ordered]@{elapsed_seconds=[math]::Round($clock.Elapsed.TotalSeconds,3);available_ram_gib=[math]::Round($available,4);owned_tree_working_set_bytes=$treeBytes;owned_pids=@($tree | ForEach-Object { [int]$_.pid })}
    if ($available -lt 0.5) { $memoryStop=$true; $killAttempted=$true; try { $p.Kill() } catch { $errorText=$_.Exception.Message }; break }
    $remaining=[int]($WaitMs-$clock.ElapsedMilliseconds)
    if ($remaining -le 0) { $deadlineReached=$true; $deadlineObservedElapsed=$clock.Elapsed.TotalSeconds; break }
    $waitReturned=[bool]$p.WaitForExit([math]::Min(200,$remaining)); $waitReturnedElapsed=$clock.Elapsed.TotalSeconds
    if ($waitReturned) { $exitObserved=$true; $exitObservedElapsed=$waitReturnedElapsed; if ($waitReturnedElapsed -ge $deadlineSeconds) { $deadlineReached=$true; $deadlineObservedElapsed=$waitReturnedElapsed }; break }
    if ($waitReturnedElapsed -ge $deadlineSeconds) { $deadlineReached=$true; $deadlineObservedElapsed=$waitReturnedElapsed; break }
    if ($p.HasExited) { $exitObserved=$true; $exitObservedElapsed=$clock.Elapsed.TotalSeconds; if($exitObservedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$exitObservedElapsed}; break }
  }
  $exitObservedBeforeCleanup=[bool]($exitObserved -and $null -ne $exitObservedElapsed -and [double]$exitObservedElapsed -lt $deadlineSeconds)
  if ($deadlineReached -and -not $exitObservedBeforeCleanup -and -not $memoryStop) { $killAttempted=$true; try { $p.Kill() } catch { $errorText=$_.Exception.Message } }
  $cleanupClock=[System.Diagnostics.Stopwatch]::StartNew()
  while (-not $p.HasExited -and $cleanupClock.ElapsedMilliseconds -lt $CleanupMs) { [void]$p.WaitForExit([math]::Min(100,[math]::Max(1,$CleanupMs-[int]$cleanupClock.ElapsedMilliseconds))) }
  $exitConfirmed=[bool]$p.HasExited; $exitCode=$null; $processExitUtc=$null
  if($exitConfirmed -and -not $exitObserved){$exitObserved=$true;$exitObservedElapsed=$clock.Elapsed.TotalSeconds}
  if ($exitConfirmed) { try { $exitCode=[int]$p.ExitCode; $processExitUtc=$p.ExitTime.ToUniversalTime().ToString('o') } catch { $exitConfirmed=$false; $errorText=$_.Exception.Message } }
  $drained=$false; $stdout=''; $stderr=''
  if ($exitConfirmed) {
    try {
      $remainingDrain=[math]::Max(1,1000-[int]$cleanupClock.ElapsedMilliseconds)
      $tasks=@($stdoutTask,$stderrTask)
      $drained=[bool][System.Threading.Tasks.Task]::WaitAll($tasks,$remainingDrain)
      if ($drained) { $stdout=[string]$stdoutTask.Result; $stderr=[string]$stderrTask.Result }
    } catch { $errorText=$_.Exception.Message }
  }
  foreach ($row in @(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation)) { $seen[[string]$row.pid]=$row }
  $residuals=@(Get-OwnedResiduals -Seen $seen); $treeClear=$residuals.Count -eq 0
  $classification=Get-ProcessClassification -DeadlineReached $deadlineReached -MemoryStop $memoryStop -ExitObserved $exitObserved -ExitObservedElapsedSeconds $exitObservedElapsed -WaitReturned $waitReturned -WaitReturnedElapsedSeconds $waitReturnedElapsed -DeadlineSeconds $deadlineSeconds -ExitCodeKnown $exitConfirmed -ExitCode $(if($null -ne $exitCode){[int]$exitCode}else{-1})
  $timedOut=[bool]($classification -eq 'deadline_timeout')
  $expectedMatches=($exitConfirmed -and ($exitCode -is [int]) -and $exitCode -eq $Expected)
  $markerOut=if ($Label -eq 'immediate_exit_0') {'probe0-out'} elseif ($Label -eq 'immediate_exit_7') {'probe7-out'} elseif ($Label -eq 'monitored_success') {'probe-sleep-out'} else {$null}
  $markerErr=if ($Label -eq 'immediate_exit_0') {'probe0-err'} elseif ($Label -eq 'immediate_exit_7') {'probe7-err'} elseif ($Label -eq 'monitored_success') {'probe-sleep-err'} else {$null}
  $markers=if ($markerOut) { $stdout.Contains($markerOut) -and $stderr.Contains($markerErr) } else {$true}
  $completed=[bool]($expectedMatches -and $classification -in @('completed','nonzero_exit') -and $drained -and $treeClear -and $markers -and (($Label -eq 'immediate_exit_7') -or $classification -eq 'completed'))
  $record=[ordered]@{label=$Label;command=@($python)+$args;pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');expected_exit_code=$Expected;exit_code=$exitCode;process_exit_utc=$processExitUtc;exit_confirmed=$exitConfirmed;wait_returned=$waitReturned;wait_returned_elapsed_seconds=$waitReturnedElapsed;exit_observed=$exitObserved;exit_observed_elapsed_seconds=$exitObservedElapsed;deadline_observed_elapsed_seconds=$deadlineObservedElapsed;wait_deadline_seconds=$deadlineSeconds;has_exited_after_wait=$exitConfirmed;actual_wait_deadline_reached=$deadlineReached;exit_observed_before_cleanup=$exitObservedBeforeCleanup;timed_out=$timedOut;memory_stop=$memoryStop;kill_attempted=$killAttempted;classification=$classification;elapsed_seconds=$clock.Elapsed.TotalSeconds;wait_timeout_seconds=$WaitMs/1000.0;cleanup_timeout_seconds=$CleanupMs/1000.0;cleanup_elapsed_seconds=$cleanupClock.Elapsed.TotalSeconds;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;stdout_marker_present=if($markerOut){$stdout.Contains($markerOut)}else{$null};stderr_marker_present=if($markerErr){$stderr.Contains($markerErr)}else{$null};completed=$completed;error=$errorText}
  $p.Dispose(); $script:ProbeRows+=@($record); if($script:WrapperReceiptPath){Save-WrapperReceipt 'running' $null}; $record
}
function Invoke-Auditor([string]$RunMode,[int]$WaitMs) {
  $ramBefore=Get-FreeRamGiB; $pythonBefore=Get-PythonInventory
  if($ramBefore -lt 0.5){throw "Auditor RAM precheck below 0.5 GiB for $RunMode"}
  if($pythonBefore.Count -gt 0){throw "Concurrent Python process found before auditor $RunMode"}
  $modeRemaining=Get-ModeRemainingMs
  if($modeRemaining -le 3000){throw "Insufficient wrapper-mode budget to start auditor $RunMode"}
  $WaitMs=[math]::Min($WaitMs,$modeRemaining-3000)
  $psi=[System.Diagnostics.ProcessStartInfo]::new(); $psi.FileName=$python; $psi.WorkingDirectory=$taskRoot
  $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
  $args=@('-B','-S',$auditor,'--root',$taskRoot,'--mode',$RunMode); $psi.Arguments=(($args | ForEach-Object { ConvertTo-Arg ([string]$_) }) -join ' ')
  $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1'; $psi.EnvironmentVariables['PYTHONUTF8']='1'; $psi.EnvironmentVariables['PYTHONNOUSERSITE']='1'
  [void]$psi.EnvironmentVariables.Remove('PYTHONPATH'); [void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new(); $p.StartInfo=$psi; $clock=[System.Diagnostics.Stopwatch]::StartNew()
  $startedUtc=[DateTime]::UtcNow.ToString('o'); $started=$p.Start(); if(-not $started){throw 'auditor Process.Start returned false'}
  $pidValue=[int]$p.Id; $creation=$p.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); $outTask=$p.StandardOutput.ReadToEndAsync(); $errTask=$p.StandardError.ReadToEndAsync()
  $seen=@{};$seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $samples=@();$minRam=$ramBefore; $deadlineSeconds=$WaitMs/1000.0; $deadlineReached=$false; $deadlineObservedElapsed=$null; $waitReturned=$false; $waitReturnedElapsed=$null; $exitObserved=$false; $exitObservedElapsed=$null; $memoryStop=$false
  while($true){
    if($p.HasExited){$exitObserved=$true;$exitObservedElapsed=$clock.Elapsed.TotalSeconds;if($exitObservedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$exitObservedElapsed};break}
    $remaining=[int]($WaitMs-$clock.ElapsedMilliseconds);if($remaining -le 0){$deadlineReached=$true;$deadlineObservedElapsed=$clock.Elapsed.TotalSeconds;break}
    $available=Get-FreeRamGiB;if($available -lt $minRam){$minRam=$available}
    $tree=@(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation);foreach($row in $tree){$seen[[string]$row.pid]=$row}
    $samples+= [ordered]@{elapsed_seconds=[math]::Round($clock.Elapsed.TotalSeconds,3);available_ram_gib=[math]::Round($available,4);owned_pids=@($tree|ForEach-Object{[int]$_.pid})}
    if($available -lt 0.5){$memoryStop=$true;try{$p.Kill()}catch{};break}
    $remaining=[int]($WaitMs-$clock.ElapsedMilliseconds);if($remaining -le 0){$deadlineReached=$true;$deadlineObservedElapsed=$clock.Elapsed.TotalSeconds;break}
    $waitReturned=[bool]$p.WaitForExit([math]::Min(250,$remaining));$waitReturnedElapsed=$clock.Elapsed.TotalSeconds
    if($waitReturned){$exitObserved=$true;$exitObservedElapsed=$waitReturnedElapsed;if($waitReturnedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$waitReturnedElapsed};break}
    if($waitReturnedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$waitReturnedElapsed;break}
    if($p.HasExited){$exitObserved=$true;$exitObservedElapsed=$clock.Elapsed.TotalSeconds;if($exitObservedElapsed -ge $deadlineSeconds){$deadlineReached=$true;$deadlineObservedElapsed=$exitObservedElapsed};break}
  }
  $killAttempted=if($memoryStop){$true}else{$false};if($deadlineReached -and -not $memoryStop -and -not ($exitObserved -and $null -ne $exitObservedElapsed -and [double]$exitObservedElapsed -lt $deadlineSeconds)){$killAttempted=$true;try{$p.Kill()}catch{}}
  $cleanup=[System.Diagnostics.Stopwatch]::StartNew();while(-not $p.HasExited -and $cleanup.ElapsedMilliseconds -lt 1000){[void]$p.WaitForExit([math]::Min(100,[math]::Max(1,1000-[int]$cleanup.ElapsedMilliseconds)))}
  $exitConfirmed=[bool]$p.HasExited;$exitCode=$null;$processExitUtc=$null;if($exitConfirmed){try{$exitCode=[int]$p.ExitCode;$processExitUtc=$p.ExitTime.ToUniversalTime().ToString('o')}catch{$exitConfirmed=$false}}
  if($exitConfirmed -and -not $exitObserved){$exitObserved=$true;$exitObservedElapsed=$clock.Elapsed.TotalSeconds}
  $drained=$false;$stdout='';$stderr='';if($exitConfirmed){try{$drained=[bool][System.Threading.Tasks.Task]::WaitAll(@($outTask,$errTask),1000);if($drained){$stdout=[string]$outTask.Result;$stderr=[string]$errTask.Result}}catch{}}
  foreach($row in @(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation)){$seen[[string]$row.pid]=$row};$residuals=@(Get-OwnedResiduals -Seen $seen);$treeClear=$residuals.Count -eq 0
  $classification=Get-ProcessClassification -DeadlineReached $deadlineReached -MemoryStop $memoryStop -ExitObserved $exitObserved -ExitObservedElapsedSeconds $exitObservedElapsed -WaitReturned $waitReturned -WaitReturnedElapsedSeconds $waitReturnedElapsed -DeadlineSeconds $deadlineSeconds -ExitCodeKnown $exitConfirmed -ExitCode $(if($null -ne $exitCode){[int]$exitCode}else{-1})
  $record=[ordered]@{pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');process_exit_utc=$processExitUtc;command=@($python)+$args;wait_timeout_seconds=$WaitMs/1000.0;wait_deadline_seconds=$deadlineSeconds;actual_wait_deadline_reached=$deadlineReached;deadline_observed_elapsed_seconds=$deadlineObservedElapsed;wait_returned=$waitReturned;wait_returned_elapsed_seconds=$waitReturnedElapsed;exit_observed=$exitObserved;exit_observed_elapsed_seconds=$exitObservedElapsed;classification=$classification;timed_out=($classification -eq 'deadline_timeout');memory_stop=$memoryStop;kill_attempted=$killAttempted;exit_confirmed=$exitConfirmed;exit_code=$exitCode;stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;elapsed_seconds=$clock.Elapsed.TotalSeconds;completed=($classification -eq 'completed' -and $drained -and $treeClear)}
  $p.Dispose();$script:AuditorRecord=$record; if($script:WrapperReceiptPath){Save-WrapperReceipt 'running' $null};$record
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Required base Python executable is missing' }
if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) { throw 'Saved M4 auditor source is missing' }
Set-Location -LiteralPath $taskRoot
$mapPath=Join-Path $roundDir 'review/approved_sources.json'; if(-not(Test-Path -LiteralPath $mapPath -PathType Leaf)){throw 'Independent approved source map missing'}
$mapHashBefore=Get-Sha256 $mapPath; $approved=Get-Content -Raw -Encoding UTF8 $mapPath | ConvertFrom-Json
if($approved.schema -ne 'round017_approved_sources.v1' -or $approved.round -ne 'round_017'){throw 'Approved source map schema/round mismatch'}
$manifestPath=Join-Path $PSScriptRoot 'candidate_sources.json';$ackPath=Join-Path $PSScriptRoot 'author_freeze_ack.json'
$manifestHashBefore=Get-Sha256 $manifestPath;$ackHashBefore=Get-Sha256 $ackPath
$sourceHashesBefore=@{};foreach($relative in $relativeSources){$path=Join-Path $taskRoot ($relative.Replace('/','\'));$prop=$approved.sha256.PSObject.Properties[$relative];if(-not $prop){throw "Approved map missing $relative"};$actual=Get-Sha256 $path;if($actual -ne ([string]$prop.Value).ToLowerInvariant()){throw "Approved source mismatch: $relative"};$sourceHashesBefore[$relative]=$actual}
$availableBefore=Get-FreeRamGiB;$pythonBefore=Get-PythonInventory
$runId=switch($Mode){'smoke'{'smoke_01'}'mock'{'mock_01'}'audit'{'audit_01'}}
$runDir=Join-Path $roundDir ("logs/"+$runId);New-Item -ItemType Directory -Force -Path $runDir | Out-Null
if((Test-Path -LiteralPath (Join-Path $runDir 'execution.claim')) -or (Test-Path -LiteralPath (Join-Path $runDir 'receipt.json'))){throw "Duplicate execution forbidden for $runId"}
$claim=[ordered]@{schema='round017_execution_claim.v1';run_id=$runId;mode=$Mode;claimed_utc=[DateTime]::UtcNow.ToString('o');approved_map_sha256=$mapHashBefore;source_hashes=$sourceHashesBefore}
$claimPath=Join-Path $runDir 'execution.claim';$claimBytes=[System.Text.UTF8Encoding]::new($false).GetBytes((ConvertTo-Json -InputObject $claim -Depth 8)+"`n");$claimStream=[System.IO.File]::Open($claimPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None);try{$claimStream.Write($claimBytes,0,$claimBytes.Length)}finally{$claimStream.Dispose()}
$script:ProbeRows=@();$script:AuditorRecord=$null;$script:WrapperReceiptPath=Join-Path $runDir 'wrapper_receipt.json'
try {
Save-WrapperReceipt 'running' $null
if($Mode -eq 'mock'){
  $cases=@(
    [ordered]@{case='deadline_before';actual=(Get-ProcessClassification -DeadlineReached $true -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -WaitReturned $true -WaitReturnedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeKnown $true -ExitCode 0);expected='completed'},
    [ordered]@{case='deadline_after';actual=(Get-ProcessClassification -DeadlineReached $true -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.7 -WaitReturned $false -WaitReturnedElapsedSeconds 0.5 -DeadlineSeconds 0.5 -ExitCodeKnown $true -ExitCode 0);expected='deadline_timeout'},
    [ordered]@{case='deadline_boundary';actual=(Get-ProcessClassification -DeadlineReached $true -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.5 -WaitReturned $true -WaitReturnedElapsedSeconds 0.5 -DeadlineSeconds 0.5 -ExitCodeKnown $true -ExitCode 0);expected='indeterminate'},
    [ordered]@{case='memory_stop';actual=(Get-ProcessClassification -DeadlineReached $false -MemoryStop $true -ExitObserved $true -ExitObservedElapsedSeconds 0.2 -WaitReturned $false -WaitReturnedElapsedSeconds 0.2 -DeadlineSeconds 0.5 -ExitCodeKnown $true -ExitCode 1);expected='memory_stop'}
  )
  foreach($case in $cases){$case['passed']=($case.actual -eq $case.expected);if(-not $case.passed){throw "Production classifier mock failed: $($case.case)"}}
  [System.IO.File]::WriteAllText((Join-Path $runDir 'classifier_cases.json'),(ConvertTo-Json -InputObject ([ordered]@{schema='round017_classifier_cases.v1';production_function='Get-ProcessClassification';cases=$cases}) -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
}
if($Mode -eq 'smoke'){
  if($availableBefore -lt 0.5){throw 'Smoke batch RAM start gate below 0.5 GiB'}
  $batchStartedUtc=[DateTime]::UtcNow.ToString('o');$batchClock=[System.Diagnostics.Stopwatch]::StartNew();$probes=@()
  $probes+=Invoke-Probe 'immediate_exit_0' "import sys; print('probe0-out'); print('probe0-err', file=sys.stderr); raise SystemExit(0)" 0 2500 1000
  $probes+=Invoke-Probe 'immediate_exit_7' "import sys; print('probe7-out'); print('probe7-err', file=sys.stderr); raise SystemExit(7)" 7 2500 1000
  $probes+=Invoke-Probe 'monitored_success' "import sys,time; time.sleep(1.2); print('probe-sleep-out'); print('probe-sleep-err', file=sys.stderr); raise SystemExit(0)" 0 5000 1000
  $probes+=Invoke-Probe 'deadline_timeout' 'import time; time.sleep(5.0)' 0 500 1000
  $completed=[bool]($probes.Count -eq 4 -and $script:ModeClock.Elapsed.TotalSeconds -le 15 -and @($probes[0..2] | Where-Object { -not $_.completed }).Count -eq 0 -and $probes[3].timed_out -and $probes[3].exit_confirmed -and $probes[3].stdout_stderr_drained -and $probes[3].owned_tree_clear)
  $probeReceipt=[ordered]@{schema='round017_process_probe_batch.v1';completed=$completed;started_utc=$batchStartedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');elapsed_seconds=$batchClock.Elapsed.TotalSeconds;timeout_seconds=15;available_ram_gib_before=$availableBefore;other_python_processes_before=$pythonBefore;probes=$probes;wait_false_alone_created_timeout=$false}
  $json=ConvertTo-Json -InputObject $probeReceipt -Depth 20;$enc=[System.Text.UTF8Encoding]::new($false);[System.IO.File]::WriteAllText((Join-Path $runDir 'probe_receipt.json'),$json+"`n",$enc)
  if(-not $completed){throw 'Process-control probe batch failed; receipt preserved'}
}
$waitMs=if($Mode -eq 'smoke'){12000}else{25000};$auditorRecord=Invoke-Auditor -RunMode $Mode -WaitMs $waitMs
$script:AuditorRecord=$auditorRecord
$manifestHashAfter=Get-Sha256 $manifestPath;$ackHashAfter=Get-Sha256 $ackPath;$mapHashAfter=Get-Sha256 $mapPath
$sourceHashesAfter=@{};foreach($relative in $relativeSources){$path=Join-Path $taskRoot ($relative.Replace('/','\'));$sourceHashesAfter[$relative]=Get-Sha256 $path}
$sourceStable=($manifestHashBefore -eq $manifestHashAfter -and $ackHashBefore -eq $ackHashAfter -and $mapHashBefore -eq $mapHashAfter)
foreach($relative in $relativeSources){if($sourceHashesBefore[$relative] -ne $sourceHashesAfter[$relative]){$sourceStable=$false}}
$auditorRecord['post_hashes_stable']=$sourceStable;$auditorRecord['approved_map_sha256_before']=$mapHashBefore;$auditorRecord['approved_map_sha256_after']=$mapHashAfter
$auditorRecord['candidate_manifest_sha256_before']=$manifestHashBefore;$auditorRecord['candidate_manifest_sha256_after']=$manifestHashAfter;$auditorRecord['author_ack_sha256_before']=$ackHashBefore;$auditorRecord['author_ack_sha256_after']=$ackHashAfter
$procPath=Join-Path $runDir 'auditor_process.json';[System.IO.File]::WriteAllText($procPath,(ConvertTo-Json -InputObject $auditorRecord -Depth 12)+"`n",[System.Text.UTF8Encoding]::new($false))
$receiptPath=Join-Path $runDir 'receipt.json'
if(Test-Path -LiteralPath $receiptPath){$modeReceipt=Get-Content -Raw -Encoding UTF8 $receiptPath | ConvertFrom-Json;$modeReceipt | Add-Member -NotePropertyName wrapper_process -NotePropertyValue $auditorRecord -Force;$modeReceipt | Add-Member -NotePropertyName approved_map_sha256_after -NotePropertyValue $mapHashAfter -Force;$modeReceipt | Add-Member -NotePropertyName source_hashes_after -NotePropertyValue $sourceHashesAfter -Force;if(-not $sourceStable -or -not $auditorRecord.completed){$modeReceipt.completed=$false};[System.IO.File]::WriteAllText($receiptPath,(ConvertTo-Json -InputObject $modeReceipt -Depth 20)+"`n",[System.Text.UTF8Encoding]::new($false))}
if($script:ModeClock.ElapsedMilliseconds -ge $script:ModeBudgetMs){$auditorRecord.completed=$false;$auditorRecord['mode_budget_exceeded']= $true}
if($auditorRecord.stdout){[Console]::Out.Write($auditorRecord.stdout)};if($auditorRecord.stderr){[Console]::Error.Write($auditorRecord.stderr)}
$success=[bool]($auditorRecord.completed -and $sourceStable -and $script:ModeClock.ElapsedMilliseconds -lt $script:ModeBudgetMs)
Save-WrapperReceipt $(if($success){'completed'}else{'failed'}) $(if($success){$null}else{'wrapper result failed or total monotonic mode budget exceeded'})
if($script:ModeClock.ElapsedMilliseconds -ge $script:ModeBudgetMs){Save-WrapperReceipt 'failed' 'total monotonic mode budget exceeded during wrapper receipt write';exit 4}
if(-not $success){exit 4}
exit $auditorRecord.exit_code
} catch {
  try { Save-WrapperReceipt 'failed' $_.Exception.Message } catch { }
  throw
}
