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
$relativeSources = @('rounds/round_019/code/saved_m4_audit.py','rounds/round_019/code/run_saved_m4_audit.ps1')

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
function Get-ProcessClassification(
  [bool]$MemoryStop,[bool]$ExitObserved,[object]$ExitObservedElapsedSeconds,[double]$DeadlineSeconds,
  [bool]$ExitCodeReadSucceeded,[int]$ExitCode,[bool]$ExitTimeValid,
  [bool]$TerminationWaitReturned,[bool]$HasExitedAfterTerminationWait,
  [bool]$StillRunningObservedAfterDeadline,[object]$StillRunningObservedElapsedSeconds,
  [bool]$KillAttempted,[object]$KillAttemptedElapsedSeconds
) {
  if ($MemoryStop) { return 'memory_stop' }
  if ($StillRunningObservedAfterDeadline -and $null -ne $StillRunningObservedElapsedSeconds -and
      [double]$StillRunningObservedElapsedSeconds -gt $DeadlineSeconds -and $KillAttempted -and
      $null -ne $KillAttemptedElapsedSeconds -and [double]$KillAttemptedElapsedSeconds -ge [double]$StillRunningObservedElapsedSeconds) {
    return 'deadline_timeout'
  }
  if (-not $ExitObserved -or $null -eq $ExitObservedElapsedSeconds -or
      -not $TerminationWaitReturned -or -not $HasExitedAfterTerminationWait -or
      -not $ExitCodeReadSucceeded -or -not $ExitTimeValid -or $ExitCode -eq -1) { return 'indeterminate' }
  if ([double]$ExitObservedElapsedSeconds -lt $DeadlineSeconds) {
    if ($ExitCode -eq 0) { return 'completed' }
    return 'nonzero_exit'
  }
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
function Get-ElapsedSinceStart([long]$StartedMonotonicTicks) { ([System.Diagnostics.Stopwatch]::GetTimestamp()-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency }
function Invoke-RecordedWait([System.Diagnostics.Process]$Process,[long]$StartedMonotonicTicks,[long]$DeadlineMonotonicTicks,[int]$MaximumWaitMs) {
  $begin=[System.Diagnostics.Stopwatch]::GetTimestamp();$remainingTicks=$DeadlineMonotonicTicks-$begin
  $requestMs=[int][math]::Max(1,[math]::Min($MaximumWaitMs,[math]::Ceiling($remainingTicks*1000.0/[System.Diagnostics.Stopwatch]::Frequency)))
  $result=$null;$errorText=$null
  try { $result=[bool]$Process.WaitForExit($requestMs) } catch { $errorText=$_.Exception.Message }
  $end=[System.Diagnostics.Stopwatch]::GetTimestamp()
  [ordered]@{begin_monotonic_ticks=$begin;begin_elapsed_seconds=($begin-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency;requested_ms=$requestMs;end_monotonic_ticks=$end;end_elapsed_seconds=($end-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency;result=$result;error=$errorText}
}
function Complete-ProcessControl([System.Diagnostics.Process]$Process,[long]$StartedMonotonicTicks,[long]$DeadlineMonotonicTicks,[int]$CleanupMs,[bool]$MemoryStop,[bool]$ControlFailure,[bool]$PriorExitObserved,[object]$PriorExitObservedElapsedSeconds) {
  $deadlineSeconds=($DeadlineMonotonicTicks-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency
  $now=[System.Diagnostics.Stopwatch]::GetTimestamp();$deadlineReached=($now -ge $DeadlineMonotonicTicks)
  $deadlineObservedElapsed=if($deadlineReached){($now-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency}else{$null}
  $postDeadlineObserved=$false;$stillRunningAfterDeadline=$false;$postDeadlineElapsed=$null;$postDeadlineBegin=$null;$postDeadlineEnd=$null;$postDeadlineError=$null
  $killAttempted=$false;$killAttemptedElapsed=$null;$killSucceeded=$false;$killError=$null
  if($deadlineReached -and -not $MemoryStop){
    while([System.Diagnostics.Stopwatch]::GetTimestamp() -le $DeadlineMonotonicTicks){[System.Threading.Thread]::Sleep(1)}
    $postDeadlineBegin=[System.Diagnostics.Stopwatch]::GetTimestamp();$alreadyExited=$false;$observationError=$null
    try{$alreadyExited=[bool]$Process.HasExited}catch{$observationError=$_.Exception.Message;$postDeadlineError=$observationError}
    $postDeadlineEnd=[System.Diagnostics.Stopwatch]::GetTimestamp();$postDeadlineElapsed=($postDeadlineEnd-$StartedMonotonicTicks)/[double][System.Diagnostics.Stopwatch]::Frequency
    $postDeadlineObserved=($null -eq $observationError -and $postDeadlineBegin -gt $DeadlineMonotonicTicks)
    if($postDeadlineObserved){$stillRunningAfterDeadline=(-not $alreadyExited)}
    if($stillRunningAfterDeadline -or -not $postDeadlineObserved){$killAttempted=$true;$killAttemptedElapsed=Get-ElapsedSinceStart $StartedMonotonicTicks;try{$Process.Kill();$killSucceeded=$true}catch{$killError=$_.Exception.Message}}
  } elseif($MemoryStop){
    $killAttempted=$true;$killAttemptedElapsed=Get-ElapsedSinceStart $StartedMonotonicTicks;try{$Process.Kill();$killSucceeded=$true}catch{$killError=$_.Exception.Message}
  } elseif($ControlFailure){
    $killAttempted=$true;$killAttemptedElapsed=Get-ElapsedSinceStart $StartedMonotonicTicks;try{$Process.Kill();$killSucceeded=$true}catch{$killError=$_.Exception.Message}
  }
  $terminationClock=[System.Diagnostics.Stopwatch]::StartNew();$terminationBegin=[System.Diagnostics.Stopwatch]::GetTimestamp();$terminationResult=$null;$terminationError=$null
  try{$terminationResult=[bool]$Process.WaitForExit($CleanupMs)}catch{$terminationError=$_.Exception.Message}
  $terminationEnd=[System.Diagnostics.Stopwatch]::GetTimestamp();$terminationElapsed=$terminationClock.Elapsed.TotalSeconds
  $hasExitedAfterWait=$false;$hasExitedReadSucceeded=$false;$hasExitedReadError=$null
  try{$hasExitedAfterWait=[bool]$Process.HasExited;$hasExitedReadSucceeded=$true}catch{$hasExitedReadError=$_.Exception.Message}
  $exitObserved=($PriorExitObserved -or $hasExitedAfterWait);$exitObservedElapsed=if($PriorExitObserved){$PriorExitObservedElapsedSeconds}elseif($hasExitedAfterWait){Get-ElapsedSinceStart $StartedMonotonicTicks}else{$null}
  $exitCode=$null;$exitCodeReadSucceeded=$false;$exitCodeReadError=$null
  if($hasExitedReadSucceeded -and $hasExitedAfterWait){try{$exitCode=[int]$Process.ExitCode;$exitCodeReadSucceeded=$true}catch{$exitCodeReadError=$_.Exception.Message}}
  $rawExitTime=$null;$processExitUtc=$null;$exitTimeReadSucceeded=$false;$exitTimeValid=$false;$exitTimeReadError=$null
  if($hasExitedReadSucceeded -and $hasExitedAfterWait){
    try{$raw=[datetime]$Process.ExitTime;$rawExitTime=$raw.ToString('o');$utc=$raw.ToUniversalTime();$processExitUtc=$utc.ToString('o');$exitTimeReadSucceeded=$true;$zero=[datetime]::FromFileTimeUtc(0);$exitTimeValid=($utc -gt $zero -and $utc.Year -gt 1601)}catch{$exitTimeReadError=$_.Exception.Message}
  }
  $terminationTimedOut=$null;if($terminationResult -is [bool]){$terminationTimedOut=(-not $terminationResult)}
  $exitCodeVerifiedNatural=($PriorExitObserved -and $null -ne $PriorExitObservedElapsedSeconds -and [double]$PriorExitObservedElapsedSeconds -lt $deadlineSeconds -and -not $killAttempted -and -not $MemoryStop -and $terminationResult -eq $true -and $hasExitedAfterWait -and $exitCodeReadSucceeded -and $exitCode -ne -1 -and $exitTimeValid)
  [ordered]@{deadline_seconds=$deadlineSeconds;actual_deadline_reached=$deadlineReached;deadline_observed_elapsed_seconds=$deadlineObservedElapsed;post_deadline_live_observation=$postDeadlineObserved;post_deadline_observation_begin_monotonic_ticks=$postDeadlineBegin;post_deadline_observation_end_monotonic_ticks=$postDeadlineEnd;post_deadline_observation_elapsed_seconds=$postDeadlineElapsed;post_deadline_observation_error=$postDeadlineError;still_running_observed_after_deadline=$stillRunningAfterDeadline;kill_attempted=$killAttempted;kill_attempted_elapsed_seconds=$killAttemptedElapsed;kill_succeeded=$killSucceeded;kill_error=$killError;termination_wait_begin_monotonic_ticks=$terminationBegin;termination_wait_requested_ms=$CleanupMs;termination_wait_end_monotonic_ticks=$terminationEnd;termination_wait_elapsed_seconds=$terminationElapsed;termination_wait_returned=$terminationResult;termination_wait_timed_out=$terminationTimedOut;termination_wait_error=$terminationError;has_exited_after_termination_wait=$hasExitedAfterWait;has_exited_read_succeeded=$hasExitedReadSucceeded;has_exited_read_error=$hasExitedReadError;exit_confirmed=($terminationResult -eq $true -and $hasExitedReadSucceeded -and $hasExitedAfterWait);exit_observed=$exitObserved;exit_observed_elapsed_seconds=$exitObservedElapsed;exit_code=$exitCode;exit_code_read_succeeded=$exitCodeReadSucceeded;exit_code_read_error=$exitCodeReadError;raw_exit_time=$rawExitTime;process_exit_utc=$processExitUtc;exit_time_read_succeeded=$exitTimeReadSucceeded;exit_time_valid=$exitTimeValid;exit_time_read_error=$exitTimeReadError;exit_code_verified_natural=$exitCodeVerifiedNatural;termination_cleanup_elapsed_seconds=$terminationElapsed}
}
function Save-WrapperReceipt([string]$State,[string]$ErrorText) {
  $elapsed=if($script:ModeClock){$script:ModeClock.Elapsed.TotalSeconds}else{$null}
  $body=[ordered]@{schema='round019_wrapper_receipt.v1';mode=$Mode;run_id=$runId;state=$State;claimed=$true;approved_map_sha256=$mapHashBefore;source_hashes=$sourceHashesBefore;started_utc=$script:ModeStartedUtc;elapsed_seconds=$elapsed;mode_budget_seconds=if($Mode -eq 'smoke'){15}else{30};probe_records=@($script:ProbeRows);auditor_process=$script:AuditorRecord;error=$ErrorText}
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
  $ramBefore=Get-FreeRamGiB;$pythonBefore=Get-PythonInventory
  if($ramBefore -lt 0.5){throw "RAM precheck below 0.5 GiB before $Label"};if($pythonBefore.Count -gt 0){throw "Concurrent Python process found before $Label; probe not started"}
  $modeReserve=if($Mode -eq 'smoke'){4000}else{1500};$modeRemaining=Get-ModeRemainingMs;if($modeRemaining -le ($CleanupMs+$modeReserve)){throw "Insufficient wrapper-mode budget to start $Label"};$WaitMs=[math]::Min($WaitMs,$modeRemaining-$CleanupMs-$modeReserve)
  $psi=[System.Diagnostics.ProcessStartInfo]::new();$psi.FileName=$python;$psi.WorkingDirectory=$taskRoot;$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
  $args=@('-B','-S','-c',$Code);$psi.Arguments=(($args|ForEach-Object{ConvertTo-Arg ([string]$_)}) -join ' ');$psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1';$psi.EnvironmentVariables['PYTHONUTF8']='1';$psi.EnvironmentVariables['PYTHONNOUSERSITE']='1';[void]$psi.EnvironmentVariables.Remove('PYTHONPATH');[void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new();$p.StartInfo=$psi;$startedUtc=[DateTime]::UtcNow.ToString('o');if(-not $p.Start()){throw "Process.Start returned false for $Label"};$startedMono=[System.Diagnostics.Stopwatch]::GetTimestamp();$deadlineTicks=$startedMono+[long][math]::Ceiling($WaitMs*[double][System.Diagnostics.Stopwatch]::Frequency/1000.0);$deadlineSeconds=$WaitMs/1000.0
  $pidValue=[int]$p.Id;$creation=$p.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ');$stdoutTask=$p.StandardOutput.ReadToEndAsync();$stderrTask=$p.StandardError.ReadToEndAsync();$seen=@{};$seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $waitCalls=@();$waitReturned=$false;$waitReturnedElapsed=$null;$exitObserved=$false;$exitObservedElapsed=$null;$deadlineReached=$false;$deadlineObservedElapsed=$null;$memoryStop=$false;$minRam=$ramBefore;$samples=@();$errorText=$null
  while($true){
    $now=[System.Diagnostics.Stopwatch]::GetTimestamp();if($now -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=Get-ElapsedSinceStart $startedMono;break}
    $obsBegin=[System.Diagnostics.Stopwatch]::GetTimestamp();$hasExited=$false;try{$hasExited=[bool]$p.HasExited}catch{$errorText=$_.Exception.Message};$obsEnd=[System.Diagnostics.Stopwatch]::GetTimestamp()
    if($hasExited){$exitObserved=$true;$exitObservedElapsed=($obsEnd-$startedMono)/[double][System.Diagnostics.Stopwatch]::Frequency;if($obsEnd -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=$exitObservedElapsed};break}
    if($obsEnd -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=($obsEnd-$startedMono)/[double][System.Diagnostics.Stopwatch]::Frequency;break}
    $available=Get-FreeRamGiB;if($available -lt $minRam){$minRam=$available};$tree=@(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation);$treeBytes=[long]0;foreach($row in $tree){$seen[[string]$row.pid]=$row;if($row.working_set_bytes){$treeBytes += [long]$row.working_set_bytes}}
    $samples += [ordered]@{elapsed_seconds=[math]::Round((Get-ElapsedSinceStart $startedMono),3);available_ram_gib=[math]::Round($available,4);owned_tree_working_set_bytes=$treeBytes;owned_pids=@($tree|ForEach-Object{[int]$_.pid})}
    if($available -lt 0.5){$memoryStop=$true;break}
    if([System.Diagnostics.Stopwatch]::GetTimestamp() -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=Get-ElapsedSinceStart $startedMono;break}
    $wait=Invoke-RecordedWait -Process $p -StartedMonotonicTicks $startedMono -DeadlineMonotonicTicks $deadlineTicks -MaximumWaitMs 200;$waitCalls+=@($wait);$waitReturned=$wait.result;$waitReturnedElapsed=$wait.end_elapsed_seconds
    if($null -ne $wait.error){$errorText=$wait.error;break};if($wait.result -eq $true){$exitObserved=$true;$exitObservedElapsed=$wait.end_elapsed_seconds;if($wait.end_monotonic_ticks -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=$wait.end_elapsed_seconds};break};if($wait.end_monotonic_ticks -ge $deadlineTicks){$deadlineReached=$true;$deadlineObservedElapsed=$wait.end_elapsed_seconds;break}
  }
  $control=Complete-ProcessControl -Process $p -StartedMonotonicTicks $startedMono -DeadlineMonotonicTicks $deadlineTicks -CleanupMs $CleanupMs -MemoryStop $memoryStop -ControlFailure ($null -ne $errorText) -PriorExitObserved $exitObserved -PriorExitObservedElapsedSeconds $exitObservedElapsed
  $exitObserved=$control.exit_observed;$exitObservedElapsed=$control.exit_observed_elapsed_seconds;$exitConfirmed=$control.exit_confirmed;$exitCode=$control.exit_code
  $exitObservedBeforeCleanup=[bool]($exitObserved -and $null -ne $exitObservedElapsed -and [double]$exitObservedElapsed -lt $deadlineSeconds)
  $drained=$false;$stdout='';$stderr='';if($exitConfirmed){try{$drained=[bool][System.Threading.Tasks.Task]::WaitAll(@($stdoutTask,$stderrTask),1000);if($drained){$stdout=[string]$stdoutTask.Result;$stderr=[string]$stderrTask.Result}}catch{$errorText=$_.Exception.Message}}
  foreach($row in @(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation)){$seen[[string]$row.pid]=$row};$residuals=@(Get-OwnedResiduals -Seen $seen);$treeClear=$residuals.Count -eq 0
  $classification=Get-ProcessClassification -MemoryStop $memoryStop -ExitObserved $exitObserved -ExitObservedElapsedSeconds $exitObservedElapsed -DeadlineSeconds $deadlineSeconds -ExitCodeReadSucceeded $control.exit_code_read_succeeded -ExitCode $(if($null -ne $exitCode){[int]$exitCode}else{-1}) -ExitTimeValid $control.exit_time_valid -TerminationWaitReturned ($control.termination_wait_returned -eq $true) -HasExitedAfterTerminationWait $control.has_exited_after_termination_wait -StillRunningObservedAfterDeadline $control.still_running_observed_after_deadline -StillRunningObservedElapsedSeconds $control.post_deadline_observation_elapsed_seconds -KillAttempted $control.kill_attempted -KillAttemptedElapsedSeconds $control.kill_attempted_elapsed_seconds
  $timedOut=[bool]($classification -eq 'deadline_timeout');$expectedMatches=($exitConfirmed -and $control.exit_code_read_succeeded -and $exitCode -eq $Expected);$markerOut=if($Label -eq 'immediate_exit_0'){'probe0-out'}elseif($Label -eq 'immediate_exit_7'){'probe7-out'}elseif($Label -eq 'monitored_success'){'probe-sleep-out'}else{$null};$markerErr=if($Label -eq 'immediate_exit_0'){'probe0-err'}elseif($Label -eq 'immediate_exit_7'){'probe7-err'}elseif($Label -eq 'monitored_success'){'probe-sleep-err'}else{$null};$markers=if($markerOut){$stdout.Contains($markerOut)-and$stderr.Contains($markerErr)}else{$true}
  $completed=[bool]($expectedMatches -and $classification -in @('completed','nonzero_exit') -and $drained -and $treeClear -and $markers -and $control.exit_time_valid -and (($Label -eq 'immediate_exit_7') -or $classification -eq 'completed'))
  $record=[ordered]@{label=$Label;command=@($python)+$args;pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');expected_exit_code=$Expected;wait_calls=$waitCalls;wait_returned=$waitReturned;wait_returned_elapsed_seconds=$waitReturnedElapsed;process_start_monotonic_ticks=$startedMono;deadline_monotonic_ticks=$deadlineTicks;wait_deadline_seconds=$deadlineSeconds;exit_observed_before_cleanup=$exitObservedBeforeCleanup;actual_wait_deadline_reached=$control.actual_deadline_reached;timed_out=$timedOut;memory_stop=$memoryStop;classification=$classification;elapsed_seconds=(Get-ElapsedSinceStart $startedMono);wait_timeout_seconds=$deadlineSeconds;cleanup_timeout_seconds=$CleanupMs/1000.0;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;stdout_marker_present=if($markerOut){$stdout.Contains($markerOut)}else{$null};stderr_marker_present=if($markerErr){$stderr.Contains($markerErr)}else{$null};completed=$completed;error=$errorText}
  foreach($key in $control.Keys){$record[$key]=$control[$key]};$p.Dispose();$script:ProbeRows+=@($record);if($script:WrapperReceiptPath){Save-WrapperReceipt 'running' $null};$record
}
function Invoke-Auditor([string]$RunMode,[int]$WaitMs) {
  $ramBefore=Get-FreeRamGiB;$pythonBefore=Get-PythonInventory;if($ramBefore -lt 0.5){throw "Auditor RAM precheck below 0.5 GiB for $RunMode"};if($pythonBefore.Count -gt 0){throw "Concurrent Python process found before auditor $RunMode"}
  $modeRemaining=Get-ModeRemainingMs;if($modeRemaining -le 3000){throw "Insufficient wrapper-mode budget to start auditor $RunMode"};$WaitMs=[math]::Min($WaitMs,$modeRemaining-3000)
  $psi=[System.Diagnostics.ProcessStartInfo]::new();$psi.FileName=$python;$psi.WorkingDirectory=$taskRoot;$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
  $args=@('-B','-S',$auditor,'--root',$taskRoot,'--mode',$RunMode);$psi.Arguments=(($args|ForEach-Object{ConvertTo-Arg ([string]$_)}) -join ' ');$psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1';$psi.EnvironmentVariables['PYTHONUTF8']='1';$psi.EnvironmentVariables['PYTHONNOUSERSITE']='1';[void]$psi.EnvironmentVariables.Remove('PYTHONPATH');[void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $p=[System.Diagnostics.Process]::new();$p.StartInfo=$psi;$startedUtc=[DateTime]::UtcNow.ToString('o');if(-not $p.Start()){throw 'auditor Process.Start returned false'};$startedMono=[System.Diagnostics.Stopwatch]::GetTimestamp();$deadlineTicks=$startedMono+[long][math]::Ceiling($WaitMs*[double][System.Diagnostics.Stopwatch]::Frequency/1000.0);$deadlineSeconds=$WaitMs/1000.0
  $pidValue=[int]$p.Id;$creation=$p.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ');$outTask=$p.StandardOutput.ReadToEndAsync();$errTask=$p.StandardError.ReadToEndAsync();$seen=@{};$seen[[string]$pidValue]=[ordered]@{pid=$pidValue;parent_pid=$null;name=$p.ProcessName;creation_utc=$creation;working_set_bytes=[long]$p.WorkingSet64;root=$true}
  $waitCalls=@();$waitReturned=$false;$waitReturnedElapsed=$null;$exitObserved=$false;$exitObservedElapsed=$null;$memoryStop=$false;$minRam=$ramBefore;$samples=@();$errorText=$null
  while($true){
    $now=[System.Diagnostics.Stopwatch]::GetTimestamp();if($now -ge $deadlineTicks){break};$obsBegin=[System.Diagnostics.Stopwatch]::GetTimestamp();$hasExited=$false;try{$hasExited=[bool]$p.HasExited}catch{$errorText=$_.Exception.Message};$obsEnd=[System.Diagnostics.Stopwatch]::GetTimestamp()
    if($hasExited){$exitObserved=$true;$exitObservedElapsed=($obsEnd-$startedMono)/[double][System.Diagnostics.Stopwatch]::Frequency;break};if($obsEnd -ge $deadlineTicks){break}
    $available=Get-FreeRamGiB;if($available -lt $minRam){$minRam=$available};$tree=@(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation);foreach($row in $tree){$seen[[string]$row.pid]=$row};$samples += [ordered]@{elapsed_seconds=[math]::Round((Get-ElapsedSinceStart $startedMono),3);available_ram_gib=[math]::Round($available,4);owned_pids=@($tree|ForEach-Object{[int]$_.pid})}
    if($available -lt 0.5){$memoryStop=$true;break};if([System.Diagnostics.Stopwatch]::GetTimestamp() -ge $deadlineTicks){break}
    $wait=Invoke-RecordedWait -Process $p -StartedMonotonicTicks $startedMono -DeadlineMonotonicTicks $deadlineTicks -MaximumWaitMs 250;$waitCalls+=@($wait);$waitReturned=$wait.result;$waitReturnedElapsed=$wait.end_elapsed_seconds;if($null -ne $wait.error){$errorText=$wait.error;break};if($wait.result -eq $true){$exitObserved=$true;$exitObservedElapsed=$wait.end_elapsed_seconds;break};if($wait.end_monotonic_ticks -ge $deadlineTicks){break}
  }
  $control=Complete-ProcessControl -Process $p -StartedMonotonicTicks $startedMono -DeadlineMonotonicTicks $deadlineTicks -CleanupMs 1000 -MemoryStop $memoryStop -ControlFailure ($null -ne $errorText) -PriorExitObserved $exitObserved -PriorExitObservedElapsedSeconds $exitObservedElapsed;$exitObserved=$control.exit_observed;$exitObservedElapsed=$control.exit_observed_elapsed_seconds;$exitConfirmed=$control.exit_confirmed;$exitCode=$control.exit_code
  $drained=$false;$stdout='';$stderr='';if($exitConfirmed){try{$drained=[bool][System.Threading.Tasks.Task]::WaitAll(@($outTask,$errTask),1000);if($drained){$stdout=[string]$outTask.Result;$stderr=[string]$errTask.Result}}catch{$errorText=$_.Exception.Message}}
  foreach($row in @(Get-TreeRows -RootPid $pidValue -RootCreationUtc $creation)){$seen[[string]$row.pid]=$row};$residuals=@(Get-OwnedResiduals -Seen $seen);$treeClear=$residuals.Count -eq 0
  $classification=Get-ProcessClassification -MemoryStop $memoryStop -ExitObserved $exitObserved -ExitObservedElapsedSeconds $exitObservedElapsed -DeadlineSeconds $deadlineSeconds -ExitCodeReadSucceeded $control.exit_code_read_succeeded -ExitCode $(if($null -ne $exitCode){[int]$exitCode}else{-1}) -ExitTimeValid $control.exit_time_valid -TerminationWaitReturned ($control.termination_wait_returned -eq $true) -HasExitedAfterTerminationWait $control.has_exited_after_termination_wait -StillRunningObservedAfterDeadline $control.still_running_observed_after_deadline -StillRunningObservedElapsedSeconds $control.post_deadline_observation_elapsed_seconds -KillAttempted $control.kill_attempted -KillAttemptedElapsedSeconds $control.kill_attempted_elapsed_seconds
  $record=[ordered]@{pid=$pidValue;creation_utc=$creation;started_utc=$startedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');command=@($python)+$args;wait_calls=$waitCalls;wait_returned=$waitReturned;wait_returned_elapsed_seconds=$waitReturnedElapsed;process_start_monotonic_ticks=$startedMono;deadline_monotonic_ticks=$deadlineTicks;wait_timeout_seconds=$deadlineSeconds;deadline_seconds=$deadlineSeconds;exit_observed=$exitObserved;exit_observed_elapsed_seconds=$exitObservedElapsed;classification=$classification;timed_out=($classification -eq 'deadline_timeout');memory_stop=$memoryStop;elapsed_seconds=(Get-ElapsedSinceStart $startedMono);completed=($classification -eq 'completed' -and $drained -and $treeClear -and $exitConfirmed -and $control.exit_time_valid);stdout=$stdout;stderr=$stderr;stdout_stderr_drained=$drained;owned_tree_seen=@($seen.Values);owned_tree_residuals=$residuals;owned_tree_clear=$treeClear;available_ram_gib_before=$ramBefore;minimum_available_ram_gib=$minRam;other_python_processes_before=$pythonBefore;resource_samples=$samples;error=$errorText}
  foreach($key in $control.Keys){$record[$key]=$control[$key]};$p.Dispose();$script:AuditorRecord=$record;if($script:WrapperReceiptPath){Save-WrapperReceipt 'running' $null};$record
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Required base Python executable is missing' }
if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) { throw 'Saved M4 auditor source is missing' }
Set-Location -LiteralPath $taskRoot
$mapPath=Join-Path $roundDir 'review/approved_sources.json'; if(-not(Test-Path -LiteralPath $mapPath -PathType Leaf)){throw 'Independent approved source map missing'}
$mapHashBefore=Get-Sha256 $mapPath; $approved=Get-Content -Raw -Encoding UTF8 $mapPath | ConvertFrom-Json
if($approved.schema -ne 'round019_approved_sources.v1' -or $approved.round -ne 'round_019'){throw 'Approved source map schema/round mismatch'}
$manifestPath=Join-Path $PSScriptRoot 'candidate_sources.json';$ackPath=Join-Path $PSScriptRoot 'author_freeze_ack.json'
$manifestHashBefore=Get-Sha256 $manifestPath;$ackHashBefore=Get-Sha256 $ackPath
$sourceHashesBefore=@{};foreach($relative in $relativeSources){$path=Join-Path $taskRoot ($relative.Replace('/','\'));$prop=$approved.sha256.PSObject.Properties[$relative];if(-not $prop){throw "Approved map missing $relative"};$actual=Get-Sha256 $path;if($actual -ne ([string]$prop.Value).ToLowerInvariant()){throw "Approved source mismatch: $relative"};$sourceHashesBefore[$relative]=$actual}
$availableBefore=Get-FreeRamGiB;$pythonBefore=Get-PythonInventory
$runId=switch($Mode){'smoke'{'smoke_01'}'mock'{'mock_01'}'audit'{'audit_01'}}
$runDir=Join-Path $roundDir ("logs/"+$runId);New-Item -ItemType Directory -Force -Path $runDir | Out-Null
if((Test-Path -LiteralPath (Join-Path $runDir 'execution.claim')) -or (Test-Path -LiteralPath (Join-Path $runDir 'receipt.json'))){throw "Duplicate execution forbidden for $runId"}
$claim=[ordered]@{schema='round019_execution_claim.v1';run_id=$runId;mode=$Mode;claimed_utc=[DateTime]::UtcNow.ToString('o');approved_map_sha256=$mapHashBefore;source_hashes=$sourceHashesBefore}
$claimPath=Join-Path $runDir 'execution.claim';$claimBytes=[System.Text.UTF8Encoding]::new($false).GetBytes((ConvertTo-Json -InputObject $claim -Depth 8)+"`n");$claimStream=[System.IO.File]::Open($claimPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None);try{$claimStream.Write($claimBytes,0,$claimBytes.Length)}finally{$claimStream.Dispose()}
$script:ProbeRows=@();$script:AuditorRecord=$null;$script:WrapperReceiptPath=Join-Path $runDir 'wrapper_receipt.json'
try {
Save-WrapperReceipt 'running' $null
if($Mode -eq 'mock'){
  $cases=@(
    [ordered]@{case='normal_exit_0';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='completed'},
    [ordered]@{case='normal_exit_7';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 7 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='nonzero_exit'},
    [ordered]@{case='round018_timing_live_then_kill';wait_false_elapsed_seconds=0.4959699;deadline_seconds=0.5;live_elapsed_seconds=0.9381056;kill_elapsed_seconds=0.9382;exit_observed_elapsed_seconds=0.9397325;kill_after_live=$true;actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.9397325 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode -1 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $true -StillRunningObservedElapsedSeconds 0.9381056 -KillAttempted $true -KillAttemptedElapsedSeconds 0.9382);expected='deadline_timeout'},
    [ordered]@{case='late_natural_exit_no_live_evidence';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.9397325 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='indeterminate'},
    [ordered]@{case='kill_without_pre_kill_live_evidence';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.9397325 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $true -KillAttemptedElapsedSeconds 0.9382);expected='indeterminate'},
    [ordered]@{case='exact_boundary_exit';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.5 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='indeterminate'},
    [ordered]@{case='exact_boundary_live';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.7 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $true -StillRunningObservedElapsedSeconds 0.5 -KillAttempted $true -KillAttemptedElapsedSeconds 0.6);expected='indeterminate'},
    [ordered]@{case='memory_stop_priority';actual=(Get-ProcessClassification -MemoryStop $true -ExitObserved $true -ExitObservedElapsedSeconds 0.2 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 1 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $true -StillRunningObservedElapsedSeconds 0.9381056 -KillAttempted $true -KillAttemptedElapsedSeconds 0.9382);expected='memory_stop'},
    [ordered]@{case='missing_termination_provenance';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $true -TerminationWaitReturned $false -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='indeterminate'},
    [ordered]@{case='invalid_exit_time_1601';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode 0 -ExitTimeValid $false -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='indeterminate'},
    [ordered]@{case='unknown_exit_code_minus_1';actual=(Get-ProcessClassification -MemoryStop $false -ExitObserved $true -ExitObservedElapsedSeconds 0.4 -DeadlineSeconds 0.5 -ExitCodeReadSucceeded $true -ExitCode -1 -ExitTimeValid $true -TerminationWaitReturned $true -HasExitedAfterTerminationWait $true -StillRunningObservedAfterDeadline $false -StillRunningObservedElapsedSeconds $null -KillAttempted $false -KillAttemptedElapsedSeconds $null);expected='indeterminate'}
  )
  foreach($case in $cases){$case['passed']=($case.actual -eq $case.expected);if(-not $case.passed){throw "Production classifier mock failed: $($case.case)"}}
  [System.IO.File]::WriteAllText((Join-Path $runDir 'classifier_cases.json'),(ConvertTo-Json -InputObject ([ordered]@{schema='round019_classifier_cases.v1';production_function='Get-ProcessClassification';cases=$cases}) -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
}
if($Mode -eq 'smoke'){
  if($availableBefore -lt 0.5){throw 'Smoke batch RAM start gate below 0.5 GiB'}
  $batchStartedUtc=[DateTime]::UtcNow.ToString('o');$batchClock=[System.Diagnostics.Stopwatch]::StartNew();$probes=@()
  $probes+=Invoke-Probe 'immediate_exit_0' "import sys; print('probe0-out'); print('probe0-err', file=sys.stderr); raise SystemExit(0)" 0 2500 1000
  $probes+=Invoke-Probe 'immediate_exit_7' "import sys; print('probe7-out'); print('probe7-err', file=sys.stderr); raise SystemExit(7)" 7 2500 1000
  $probes+=Invoke-Probe 'monitored_success' "import sys,time; time.sleep(1.2); print('probe-sleep-out'); print('probe-sleep-err', file=sys.stderr); raise SystemExit(0)" 0 5000 1000
  $probes+=Invoke-Probe 'deadline_timeout' 'import time; time.sleep(5.0)' 0 500 1000
  $completed=[bool]($probes.Count -eq 4 -and $script:ModeClock.Elapsed.TotalSeconds -le 15 -and @($probes[0..2] | Where-Object { -not $_.completed }).Count -eq 0 -and $probes[3].timed_out -and $probes[3].still_running_observed_after_deadline -and $probes[3].kill_attempted -and $probes[3].termination_wait_returned -eq $true -and $probes[3].exit_confirmed -and $probes[3].has_exited_read_succeeded -and $probes[3].exit_code_read_succeeded -and $probes[3].exit_time_read_succeeded -and $probes[3].owned_tree_clear)
  $probeReceipt=[ordered]@{schema='round019_process_probe_batch.v1';completed=$completed;started_utc=$batchStartedUtc;finished_utc=[DateTime]::UtcNow.ToString('o');elapsed_seconds=$batchClock.Elapsed.TotalSeconds;timeout_seconds=15;available_ram_gib_before=$availableBefore;other_python_processes_before=$pythonBefore;probes=$probes;wait_false_alone_created_timeout=$false}
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
