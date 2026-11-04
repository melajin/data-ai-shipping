param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('smoke','mock','synthetic')]
  [string]$Mode
)

$ErrorActionPreference = 'Stop'
$roundDir = Split-Path -Parent $PSScriptRoot
$taskRoot = Split-Path -Parent (Split-Path -Parent $roundDir)
$mapPath = Join-Path $roundDir 'review/approved_sources.json'
$python = 'C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$relativeSources = @(
  'rounds/round_015/code/m4_synthetic.py',
  'rounds/round_015/code/test_m4_mock.py',
  'rounds/round_015/code/run_m4.ps1'
)
$roundName = 'round_015'
$minimumSyntheticRamGiB = 3.0
$stopSyntheticRamGiB = 1.5

function Get-Sha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  $encoding = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Write-Receipt([string]$Path, $Value) {
  $json = ConvertTo-Json -InputObject $Value -Depth 24
  Write-Utf8NoBom -Path $Path -Text ($json + "`n")
}

function New-ExecutionClaim([string]$Path, $Value) {
  $json = ConvertTo-Json -InputObject $Value -Depth 8 -Compress
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
  $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
  try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

function Get-AvailableRamGiB {
  $os = Get-CimInstance -ClassName Win32_OperatingSystem
  return [double]$os.FreePhysicalMemory / 1MB
}

function Get-PythonInventory {
  return @(
    Get-Process -Name 'python','pythonw' -ErrorAction SilentlyContinue | ForEach-Object {
      $creation = $null
      try { $creation = $_.StartTime.ToUniversalTime().ToString('o') } catch { }
      [ordered]@{ pid = [int]$_.Id; name = $_.ProcessName; creation_utc = $creation }
    }
  )
}

function Get-OwnedTreeSnapshot([int]$RootPid) {
  $all = @(Get-CimInstance -ClassName Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CreationDate, WorkingSetSize)
  $owned = [System.Collections.Generic.HashSet[int]]::new()
  [void]$owned.Add($RootPid)
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($item in $all) {
      $pidValue = [int]$item.ProcessId
      $parentValue = [int]$item.ParentProcessId
      if ($owned.Contains($parentValue) -and -not $owned.Contains($pidValue)) {
        [void]$owned.Add($pidValue)
        $changed = $true
      }
    }
  }
  $rows = @(
    foreach ($pidValue in $owned) {
      $cimRow = $all | Where-Object { [int]$_.ProcessId -eq $pidValue } | Select-Object -First 1
      $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
      $creation = $null
      $name = if ($process) { $process.ProcessName } elseif ($cimRow) { [string]$cimRow.Name } else { 'unknown' }
      $workingSet = $null
      if ($process) {
        try { $creation = $process.StartTime.ToUniversalTime().ToString('o') } catch { }
        try { $workingSet = [long]$process.WorkingSet64 } catch { }
      }
      if (-not $creation -and $cimRow -and $cimRow.CreationDate) {
        try { $creation = [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$cimRow.CreationDate).ToUniversalTime().ToString('o') } catch { }
      }
      if ($null -eq $workingSet -and $cimRow -and $cimRow.WorkingSetSize) {
        try { $workingSet = [long]$cimRow.WorkingSetSize } catch { }
      }
      # Keep an owned PID even when its identity cannot be read; completion then fails closed.
      [ordered]@{
        pid = $pidValue
        name = $name
        creation_utc = $creation
        working_set_bytes = $workingSet
        root = ($pidValue -eq $RootPid)
      }
    }
  )
  return $rows
}

function Test-OwnedTreeClear($SeenRows) {
  $residual = @()
  foreach ($row in $SeenRows) {
    if (-not $row.pid -or -not $row.creation_utc) {
      $residual += [ordered]@{ pid = $row.pid; residual = $true; reason = 'identity_unavailable' }
      continue
    }
    $process = Get-Process -Id ([int]$row.pid) -ErrorAction SilentlyContinue
    if ($process) {
      $creation = $null
      try { $creation = $process.StartTime.ToUniversalTime().ToString('o') } catch { }
      if (-not $creation) {
        $residual += [ordered]@{ pid = $row.pid; residual = $true; reason = 'live_process_identity_unavailable' }
      } elseif ($creation -eq $row.creation_utc) {
        $residual += [ordered]@{ pid = $row.pid; residual = $true; reason = 'same_owned_process_still_present' }
      }
    } else {
      try {
        $cimProcess = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $([int]$row.pid)"
        if ($cimProcess) {
          $residual += [ordered]@{ pid = $row.pid; residual = $true; reason = 'live_process_uninspectable_by_GetProcess' }
        }
      } catch {
        $residual += [ordered]@{ pid = $row.pid; residual = $true; reason = 'wmi_identity_check_failed'; error = $_.Exception.Message }
      }
    }
  }
  return $residual
}

function ConvertTo-WindowsCommandLineArgument([string]$Argument) {
  $builder = New-Object System.Text.StringBuilder
  $backslash = [string][char]92
  [void]$builder.Append([char]34)
  $backslashCount = 0
  foreach ($character in $Argument.ToCharArray()) {
    if ([int]$character -eq 92) { $backslashCount++; continue }
    if ([int]$character -eq 34) {
      if ($backslashCount -gt 0) { [void]$builder.Append($backslash * (2 * $backslashCount)) }
      [void]$builder.Append($backslash)
      [void]$builder.Append([char]34)
      $backslashCount = 0
      continue
    }
    if ($backslashCount -gt 0) { [void]$builder.Append($backslash * $backslashCount) }
    [void]$builder.Append($character)
    $backslashCount = 0
  }
  if ($backslashCount -gt 0) { [void]$builder.Append($backslash * (2 * $backslashCount)) }
  [void]$builder.Append([char]34)
  return $builder.ToString()
}

function Stop-OwnedDescendants([int]$RootPid, $SeenRows) {
  $scanError = $null
  $current = @()
  try { $current = @(Get-OwnedTreeSnapshot -RootPid $RootPid) } catch { $scanError = $_.Exception.Message }
  $allRows = @($SeenRows) + @($current)
  $unique = @{}
  foreach ($row in $allRows) { if ($row.pid) { $unique[[string]$row.pid] = $row } }
  $killErrors = @()
  foreach ($key in @($unique.Keys)) {
    $row = $unique[$key]
    if ($row.root -or -not $row.pid -or -not $row.creation_utc) { continue }
    $process = Get-Process -Id ([int]$row.pid) -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $creation = $null
    try { $creation = $process.StartTime.ToUniversalTime().ToString('o') } catch { }
    if ($creation -eq $row.creation_utc) {
      try { $process.Kill() } catch { $killErrors += "pid $($row.pid): $($_.Exception.Message)" }
    }
  }
  return [ordered]@{ scan_error = $scanError; descendant_kill_errors = $killErrors }
}

function Invoke-OwnedProcess(
  [string[]]$Arguments,
  [int]$WaitMilliseconds,
  [int]$CleanupMilliseconds,
  [string]$WorkingDirectory,
  [string]$ChildTempDirectory,
  [bool]$MonitorSynthetic,
  [double]$RamStopThresholdGiB
) {
  $clock = [System.Diagnostics.Stopwatch]::StartNew()
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $python
  $psi.WorkingDirectory = $WorkingDirectory
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.Arguments = (($Arguments | ForEach-Object { ConvertTo-WindowsCommandLineArgument ([string]$_) }) -join ' ')
  $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
  $psi.EnvironmentVariables['PYTHONUTF8'] = '1'
  $psi.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
  [void]$psi.EnvironmentVariables.Remove('PYTHONPATH')
  [void]$psi.EnvironmentVariables.Remove('PYTHONHOME')
  $psi.EnvironmentVariables['TMP'] = $ChildTempDirectory
  $psi.EnvironmentVariables['TEMP'] = $ChildTempDirectory
  $psi.EnvironmentVariables['TMPDIR'] = $ChildTempDirectory
  $psi.EnvironmentVariables['PYTHONPYCACHEPREFIX'] = (Join-Path $ChildTempDirectory 'pycache')
  $psi.EnvironmentVariables['HF_HOME'] = (Join-Path $ChildTempDirectory 'hf')
  $psi.EnvironmentVariables['TORCH_HOME'] = (Join-Path $ChildTempDirectory 'torch')
  $psi.EnvironmentVariables['XDG_CACHE_HOME'] = (Join-Path $ChildTempDirectory 'cache')
  $psi.EnvironmentVariables['JOBLIB_TEMP_FOLDER'] = (Join-Path $ChildTempDirectory 'joblib')
  $psi.EnvironmentVariables['MPLCONFIGDIR'] = (Join-Path $ChildTempDirectory 'mpl')
  $psi.EnvironmentVariables['OMP_NUM_THREADS'] = '3'
  $psi.EnvironmentVariables['MKL_NUM_THREADS'] = '3'
  $psi.EnvironmentVariables['OPENBLAS_NUM_THREADS'] = '3'
  $psi.EnvironmentVariables['NUMEXPR_NUM_THREADS'] = '3'
  $psi.EnvironmentVariables['HF_HUB_OFFLINE'] = '1'
  $psi.EnvironmentVariables['TRANSFORMERS_OFFLINE'] = '1'
  $psi.EnvironmentVariables['HF_HUB_DISABLE_TELEMETRY'] = '1'
  $psi.EnvironmentVariables['CUDA_VISIBLE_DEVICES'] = ''

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $psi
  $started = $false
  $waitFinished = $false
  $timedOut = $false
  $memoryStop = $false
  $killAttempted = $false
  $exitConfirmed = $false
  $exitCode = $null
  $pidValue = $null
  $creationUtc = $null
  $stdout = $null
  $stderr = $null
  $streamsDrained = $false
  $processError = $null
  $stdoutTask = $null
  $stderrTask = $null
  $minAvailableRam = $null
  $peakOwnedWorkingSet = 0L
  $resourceSamples = @()
  $seenTree = @{}
  $treeScanError = $null
  $monitorClock = [System.Diagnostics.Stopwatch]::StartNew()
  $nextSampleMilliseconds = 0
  $cleanupStartedUtc = $null
  try {
    $started = $process.Start()
    if (-not $started) { throw 'Process.Start returned false' }
    $pidValue = [int]$process.Id
    $creationUtc = $process.StartTime.ToUniversalTime().ToString('o')
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $seenTree[[string]$pidValue] = [ordered]@{
      pid = $pidValue; name = $process.ProcessName; creation_utc = $creationUtc
      working_set_bytes = [long]$process.WorkingSet64; root = $true
    }
    $deadline = [DateTime]::UtcNow.AddMilliseconds($WaitMilliseconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
      $remaining = [Math]::Max(1, [int]($deadline - [DateTime]::UtcNow).TotalMilliseconds)
      $poll = [Math]::Min(500, $remaining)
      if ($process.WaitForExit($poll)) { break }
      if ($MonitorSynthetic -and $monitorClock.ElapsedMilliseconds -ge $nextSampleMilliseconds) {
        $available = Get-AvailableRamGiB
        if ($null -eq $minAvailableRam -or $available -lt $minAvailableRam) { $minAvailableRam = $available }
        $tree = @(Get-OwnedTreeSnapshot -RootPid $pidValue)
        $treeBytes = [long]0
        foreach ($row in $tree) {
          if ($row.pid) { $seenTree[[string]$row.pid] = $row }
          if ($row.working_set_bytes) { $treeBytes += [long]$row.working_set_bytes }
        }
        if ($treeBytes -gt $peakOwnedWorkingSet) { $peakOwnedWorkingSet = $treeBytes }
        $resourceSamples += [ordered]@{
          elapsed_seconds = [Math]::Round($monitorClock.Elapsed.TotalSeconds, 3)
          available_ram_gib = [Math]::Round($available, 4)
          owned_tree_working_set_bytes = $treeBytes
          owned_pids = @($tree | ForEach-Object { [int]$_.pid })
        }
        $nextSampleMilliseconds = [long]($monitorClock.ElapsedMilliseconds + 1000)
        if ($available -lt $RamStopThresholdGiB) {
          $memoryStop = $true
          $cleanupStartedUtc = [DateTime]::UtcNow
          $processError = "Available RAM fell below $RamStopThresholdGiB GiB; stopping only the owned child tree"
          $cleanupResult = Stop-OwnedDescendants -RootPid $pidValue -SeenRows @($seenTree.Values)
          if ($cleanupResult.scan_error) { $processError += "; descendant scan error: $($cleanupResult.scan_error)" }
          if ($cleanupResult.descendant_kill_errors.Count -gt 0) { $processError += "; descendant kill errors: $($cleanupResult.descendant_kill_errors -join '; ')" }
          try { if (-not $process.HasExited) { $process.Kill(); $killAttempted = $true } }
          catch { $processError += "; root kill error: $($_.Exception.Message)" }
          break
        }
      }
    }
    $waitFinished = [bool]$process.WaitForExit(1)
    $timedOut = (-not $waitFinished) -and (-not $memoryStop)
    if (-not $waitFinished) {
      $cleanupStartedUtc = [DateTime]::UtcNow
      $cleanupResult = Stop-OwnedDescendants -RootPid $pidValue -SeenRows @($seenTree.Values)
      if ($cleanupResult.scan_error) { $processError = "descendant scan error during timeout cleanup: $($cleanupResult.scan_error)" }
      if ($cleanupResult.descendant_kill_errors.Count -gt 0) { $processError = "descendant kill errors during timeout cleanup: $($cleanupResult.descendant_kill_errors -join '; ')" }
      try {
        if (-not $process.HasExited) { $process.Kill(); $killAttempted = $true }
      } catch { $processError += "; root process cleanup failed: $($_.Exception.Message)" }
      $exitConfirmed = [bool]$process.WaitForExit($CleanupMilliseconds)
    } else {
      $exitConfirmed = [bool]$process.HasExited
    }
    if ($null -eq $cleanupStartedUtc) { $cleanupStartedUtc = [DateTime]::UtcNow }
    $remainingMilliseconds = [Math]::Max(0, $CleanupMilliseconds - [int]([DateTime]::UtcNow - $cleanupStartedUtc).TotalMilliseconds)
    if ($stdoutTask -and $stderrTask -and $remainingMilliseconds -gt 0) {
      $streamsDrained = [System.Threading.Tasks.Task]::WaitAll(
        [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask), [int]$remainingMilliseconds)
    }
    if ($streamsDrained) {
      $stdout = $stdoutTask.GetAwaiter().GetResult()
      $stderr = $stderrTask.GetAwaiter().GetResult()
    }
    $process.Refresh()
    $exitConfirmed = $exitConfirmed -or [bool]$process.HasExited
    if ($exitConfirmed) {
      $rawExitCode = $process.ExitCode
      if ($rawExitCode -is [int]) { $exitCode = $rawExitCode }
      else { $processError = 'Process exit confirmed but ExitCode was not Int32' }
    }
  } catch {
    $processError = $_.Exception.Message
    try {
      if ($started -and -not $process.HasExited) {
        $cleanupResult = Stop-OwnedDescendants -RootPid $pidValue -SeenRows @($seenTree.Values)
        if ($cleanupResult.scan_error) { $processError += "; descendant scan error: $($cleanupResult.scan_error)" }
        $process.Kill(); $killAttempted = $true
        $exitConfirmed = [bool]$process.WaitForExit($CleanupMilliseconds)
      }
    } catch { $processError += "; root kill error: $($_.Exception.Message)" }
  } finally {
    $monitorClock.Stop()
    $clock.Stop()
  }
  $ownedExited = $false
  if ($started) { try { $ownedExited = [bool]$process.HasExited } catch { } }
  if ($started) {
    try {
      $finalTree = @(Get-OwnedTreeSnapshot -RootPid $pidValue)
      foreach ($row in $finalTree) {
        if (-not $row.pid) { continue }
        # Preserve the original root identity after exit; record every final descendant.
        if ([int]$row.pid -eq [int]$pidValue) { continue }
        $seenTree[[string]$row.pid] = $row
      }
    } catch {
      $treeScanError = $_.Exception.Message
    }
  }
  $residuals = @()
  if ($started) { $residuals = @(Test-OwnedTreeClear -SeenRows @($seenTree.Values)) }
  $process.Dispose()
  return [ordered]@{
    started = $started
    pid = $pidValue
    creation_utc = $creationUtc
    wait_finished = $waitFinished
    timed_out = $timedOut
    memory_stop = $memoryStop
    kill_attempted = $killAttempted
    exit_confirmed = $exitConfirmed
    exit_code = $exitCode
    owned_process_exited = $ownedExited
    owned_tree_seen = @($seenTree.Values)
    owned_tree_residuals = $residuals
    owned_tree_final_scan_error = $treeScanError
    owned_tree_clear = ($residuals.Count -eq 0 -and -not $treeScanError)
    stdout = $stdout
    stderr = $stderr
    stdout_stderr_drained = $streamsDrained
    elapsed_seconds = $clock.Elapsed.TotalSeconds
    wait_timeout_seconds = $WaitMilliseconds / 1000.0
    cleanup_timeout_seconds = $CleanupMilliseconds / 1000.0
    minimum_available_ram_gib = $minAvailableRam
    peak_owned_tree_working_set_bytes = $peakOwnedWorkingSet
    resource_samples = $resourceSamples
    command = @($python) + $Arguments
    error = $processError
  }
}

function Read-Receipt([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-MapChecks($Approved) {
  return @(
    foreach ($relative in $relativeSources) {
      $property = $Approved.sha256.PSObject.Properties[$relative]
      $expected = if ($property) { [string]$property.Value } else { '' }
      $path = Join-Path $taskRoot ($relative.Replace('/', '\'))
      $actual = if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Sha256 $path } else { $null }
      [ordered]@{
        path = $relative
        expected_sha256 = $expected.ToLowerInvariant()
        actual_sha256 = $actual
        match = [bool]($actual -and $expected -and $actual -eq $expected.ToLowerInvariant())
      }
    }
  )
}

function Invoke-Round015 {
  if (-not (Test-Path -LiteralPath $mapPath -PathType Leaf)) { throw 'Missing review/approved_sources.json' }
  if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Required base Python executable is missing' }
  Set-Location -LiteralPath $taskRoot
  $approved = Get-Content -LiteralPath $mapPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($approved.schema -ne 'round015_approved_sources.v1' -or $approved.round -ne $roundName) {
    throw 'Unexpected approved-source map schema or round identifier'
  }
  if (-not $approved.sha256) { throw 'Approved-source SHA map is missing' }
  $actualPaths = @($approved.sha256.PSObject.Properties.Name | Sort-Object)
  $expectedPaths = @($relativeSources | Sort-Object)
  if (($actualPaths -join "`n") -ne ($expectedPaths -join "`n")) {
    throw 'Approved map must contain exactly the three round015 code files'
  }
  foreach ($relative in $relativeSources) {
    $sha = [string]$approved.sha256.$relative
    if ($sha -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid SHA-256 for $relative" }
  }
  $approvalBefore = Get-Sha256 $mapPath
  $liveBefore = @(Get-MapChecks $approved)
  if (@($liveBefore | Where-Object { -not $_.match }).Count -gt 0) { throw 'Approval/live hash mismatch before launch' }

  $otherPythonBefore = @(Get-PythonInventory)
  $availableRam = Get-AvailableRamGiB
  if ($Mode -eq 'synthetic' -and $availableRam -lt $minimumSyntheticRamGiB) {
    throw "Synthetic start RAM below $minimumSyntheticRamGiB GiB ($availableRam); complete independent work and recheck before launch"
  }
  $runId = switch ($Mode) { 'smoke' { 'smoke_01' }; 'mock' { 'mock_01' }; 'synthetic' { 'synthetic_01' } }
  $runDir = Join-Path $roundDir ("logs/" + $runId)
  $tempDir = Join-Path $roundDir ("temp/" + $runId)
  $receiptPath = Join-Path $runDir 'receipt.json'
  $claimPath = Join-Path $runDir 'execution.claim'
  if ((Test-Path -LiteralPath $receiptPath) -or (Test-Path -LiteralPath $claimPath)) {
    throw "$runId already has a receipt/claim; duplicate execution is forbidden"
  }
  if ($Mode -eq 'mock') {
    $smoke = Read-Receipt (Join-Path $roundDir 'logs/smoke_01/receipt.json')
    if (-not $smoke -or $smoke.completed -ne $true -or $smoke.approval_map_sha256_after -ne $approvalBefore) {
      throw 'A successful process smoke under this exact approval map is required before mock'
    }
  } elseif ($Mode -eq 'synthetic') {
    $mock = Read-Receipt (Join-Path $roundDir 'logs/mock_01/receipt.json')
    if (-not $mock -or $mock.completed -ne $true -or $mock.approval_map_sha256_after -ne $approvalBefore) {
      throw 'A successful stdlib mock under this exact approval map is required before synthetic execution'
    }
    foreach ($output in @('artifacts/m4_synthetic_result.json','artifacts/m4_a_head.pt','artifacts/m4_b_merged_head.pt')) {
      if (Test-Path -LiteralPath (Join-Path $roundDir $output)) { throw "Output already exists; retry forbidden: $output" }
    }
  }
  New-Item -ItemType Directory -Force -Path $runDir,$tempDir | Out-Null

  $state = [ordered]@{
    schema = 'round015_process_receipt.v1'
    mode = $Mode
    run_id = $runId
    started_utc = [DateTimeOffset]::UtcNow.ToString('o')
    completed = $false
    launched = $false
    exit_code = $null
    timeout_seconds = switch ($Mode) { 'smoke' { 10 }; 'mock' { 30 }; 'synthetic' { 180 } }
    compute_timeout_seconds = if ($Mode -eq 'synthetic') { 170 } else { $null }
    cleanup_timeout_seconds = if ($Mode -eq 'synthetic') { 10 } else { $null }
    available_ram_gib_before = $availableRam
    minimum_start_ram_gib = if ($Mode -eq 'synthetic') { $minimumSyntheticRamGiB } else { $null }
    stop_available_ram_gib_below = if ($Mode -eq 'synthetic') { $stopSyntheticRamGiB } else { $null }
    expected_peak_mib = if ($Mode -eq 'synthetic') { 1536 } else { 100 }
    expected_peak_basis = if ($Mode -eq 'synthetic') { 'planning assumption only: pinned ~105 MiB checkpoint, model load copies, Torch CPU, target cache <1 MiB; not measured' } else { 'base-Python stdlib smoke/mock only' }
    other_python_processes_before = $otherPythonBefore
    approval_map_path = 'rounds/round_015/review/approved_sources.json'
    approval_map_sha256_before = $approvalBefore
    approval_map_sha256_after = $null
    approval_map_unchanged = $false
    live_precheck = $liveBefore
    live_postcheck = @()
    source_snapshot = [ordered]@{}
    snapshots = @()
    snapshot_postcheck = @()
    children = @()
    process = $null
    stdout = $null
    stderr = $null
    owned_process_exited = $false
    owned_tree_clear = $false
    stdout_stderr_drained = $false
    f1_computed = $false
    project_data_opened = $false
    network_used = $false
    error = $null
  }
  New-ExecutionClaim -Path $claimPath -Value ([ordered]@{
    schema = 'round015_execution_claim.v1'
    run_id = $runId
    mode = $Mode
    approval_map_sha256 = $approvalBefore
    claimed_utc = $state.started_utc
  })

  try {
    $sourceDir = Join-Path $runDir 'source'
    if ((Test-Path -LiteralPath $sourceDir -PathType Container) -and (@(Get-ChildItem -LiteralPath $sourceDir -Force).Count -gt 0)) {
      throw 'Run source snapshot directory is not empty'
    }
    New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
    foreach ($relative in $relativeSources) {
      $source = Join-Path $taskRoot ($relative.Replace('/', '\'))
      $dest = Join-Path $sourceDir ([System.IO.Path]::GetFileName($source))
      Copy-Item -LiteralPath $source -Destination $dest
      $snapshotSha = Get-Sha256 $dest
      $expectedSha = ([string]$approved.sha256.$relative).ToLowerInvariant()
      $state.source_snapshot[$relative] = $dest
      $state.snapshots += [ordered]@{
        path = $relative
        snapshot_path = $dest
        expected_sha256 = $expectedSha
        snapshot_sha256 = $snapshotSha
        match = ($snapshotSha -eq $expectedSha)
      }
    }
    if (@($state.snapshots | Where-Object { -not $_.match }).Count -gt 0) {
      throw 'Copied source snapshot differs from the approved map'
    }

    if ($Mode -eq 'smoke') {
      $smokeClock = [System.Diagnostics.Stopwatch]::StartNew()
      foreach ($expectedExit in @(0,7)) {
        $remaining = [Math]::Max(1, 10000 - [int]$smokeClock.ElapsedMilliseconds)
        $cleanup = [Math]::Min(1000, [Math]::Max(0, $remaining - 1))
        $wait = [Math]::Min(4000, [Math]::Max(1, $remaining - $cleanup))
        $childCode = "import sys; print('round015_smoke_stdout_$expectedExit'); print('round015_smoke_stderr_$expectedExit', file=sys.stderr); raise SystemExit($expectedExit)"
        $child = Invoke-OwnedProcess -Arguments @('-B','-S','-c',$childCode) -WaitMilliseconds $wait `
          -CleanupMilliseconds $cleanup -WorkingDirectory $taskRoot -ChildTempDirectory $tempDir `
          -MonitorSynthetic $false -RamStopThresholdGiB 0
        $child['expected_exit_code'] = [int]$expectedExit
        $child['exit_code_matches_expected'] = (($child.exit_code -is [int]) -and ($child.exit_code -eq $expectedExit))
        $child['stdout_marker_present'] = ([string]$child.stdout).Contains("round015_smoke_stdout_$expectedExit")
        $child['stderr_marker_present'] = ([string]$child.stderr).Contains("round015_smoke_stderr_$expectedExit")
        $child['completed'] = [bool]($child.started -and $child.exit_confirmed -and $child.owned_process_exited `
          -and $child.owned_tree_clear -and $child.stdout_stderr_drained -and $child.exit_code_matches_expected `
          -and $child.stdout_marker_present -and $child.stderr_marker_present -and -not $child.timed_out)
        $state.children += $child
      }
      $smokeClock.Stop()
      $state.elapsed_seconds = $smokeClock.Elapsed.TotalSeconds
      $state.stdout = (@($state.children | ForEach-Object { $_.stdout }) -join "`n")
      $state.stderr = (@($state.children | ForEach-Object { $_.stderr }) -join "`n")
      $state.owned_process_exited = (@($state.children | Where-Object { -not $_.owned_process_exited }).Count -eq 0)
      $state.owned_tree_clear = (@($state.children | Where-Object { -not $_.owned_tree_clear }).Count -eq 0)
      $state.stdout_stderr_drained = (@($state.children | Where-Object { -not $_.stdout_stderr_drained }).Count -eq 0)
      $state.exit_code = if (@($state.children | Where-Object { -not $_.completed }).Count -eq 0) { 0 } else { 4 }
      $state.launched = (@($state.children | Where-Object { $_.started }).Count -eq 2)
    } else {
      $scriptName = if ($Mode -eq 'mock') { 'test_m4_mock.py' } else { 'm4_synthetic.py' }
      $snapshotScript = Join-Path $sourceDir $scriptName
      $arguments = @('-B','-S')
      if ($Mode -eq 'mock') {
        $arguments += @($snapshotScript)
      } else {
        $arguments += @($snapshotScript,
          '--root', $taskRoot,
          '--result', (Join-Path $roundDir 'artifacts/m4_synthetic_result.json'),
          '--progress', (Join-Path $runDir 'progress.jsonl'),
          '--temp', $tempDir)
      }
      $waitMs = if ($Mode -eq 'synthetic') { 170000 } else { 28000 }
      $cleanupMs = if ($Mode -eq 'synthetic') { 10000 } else { 2000 }
      $state.process = Invoke-OwnedProcess -Arguments $arguments -WaitMilliseconds $waitMs `
        -CleanupMilliseconds $cleanupMs -WorkingDirectory $taskRoot -ChildTempDirectory $tempDir `
        -MonitorSynthetic ($Mode -eq 'synthetic') -RamStopThresholdGiB $stopSyntheticRamGiB
      $state.launched = [bool]$state.process.started
      $state.exit_code = $state.process.exit_code
      $state.timed_out = [bool]$state.process.timed_out
      $state.memory_stop = [bool]$state.process.memory_stop
      $state.elapsed_seconds = $state.process.elapsed_seconds
      $state.minimum_available_ram_gib = $state.process.minimum_available_ram_gib
      $state.peak_owned_tree_working_set_bytes = $state.process.peak_owned_tree_working_set_bytes
      $state.resource_samples = $state.process.resource_samples
      $state.owned_process_exited = [bool]$state.process.owned_process_exited
      $state.owned_tree_clear = [bool]$state.process.owned_tree_clear
      $state.stdout_stderr_drained = [bool]$state.process.stdout_stderr_drained
      $state.stdout = $state.process.stdout
      $state.stderr = $state.process.stderr
      if ($Mode -eq 'synthetic') {
        $modelResult = Read-Receipt (Join-Path $roundDir 'artifacts/m4_synthetic_result.json')
        $state.synthetic_result_status = if ($modelResult) { $modelResult.status } else { $null }
        $state.call_counts = if ($modelResult) { $modelResult.call_counts } else { $null }
        if (-not $modelResult -or $modelResult.status -ne 'completed') {
          $state.error = 'Synthetic child did not write a completed result artifact'
        }
      }
    }
  } catch {
    $state.error = $_.Exception.Message
  } finally {
    $state.finished_utc = [DateTimeOffset]::UtcNow.ToString('o')
    try { $state.live_postcheck = @(Get-MapChecks $approved) } catch { $state.live_postcheck_error = $_.Exception.Message }
    try { $state.approval_map_sha256_after = Get-Sha256 $mapPath } catch { $state.approval_map_postcheck_error = $_.Exception.Message }
    $state.approval_map_unchanged = [bool]($state.approval_map_sha256_before -and $state.approval_map_sha256_after `
      -and $state.approval_map_sha256_before -eq $state.approval_map_sha256_after)
    $state.snapshot_postcheck = @(
      foreach ($snapshot in $state.snapshots) {
        $current = if (Test-Path -LiteralPath $snapshot.snapshot_path -PathType Leaf) { Get-Sha256 $snapshot.snapshot_path } else { $null }
        [ordered]@{ path = $snapshot.path; snapshot_sha256 = $current; match = [bool]($current -and $current -eq $snapshot.expected_sha256) }
      }
    )
    $state.other_python_processes_after = @(Get-PythonInventory)
    $liveOk = @($state.live_postcheck).Count -eq $relativeSources.Count `
      -and @($state.live_postcheck | Where-Object { -not $_.match }).Count -eq 0
    $snapshotOk = @($state.snapshots).Count -eq $relativeSources.Count `
      -and @($state.snapshots | Where-Object { -not $_.match }).Count -eq 0 `
      -and @($state.snapshot_postcheck).Count -eq $relativeSources.Count `
      -and @($state.snapshot_postcheck | Where-Object { -not $_.match }).Count -eq 0
    $commonOk = [bool]($state.launched -and $state.approval_map_unchanged -and $liveOk -and $snapshotOk)
    if ($Mode -eq 'smoke') {
      $childrenOk = @($state.children).Count -eq 2 -and @($state.children | Where-Object { -not $_.completed }).Count -eq 0
      $state.completed = [bool]($commonOk -and $childrenOk -and $state.owned_process_exited `
        -and $state.owned_tree_clear -and $state.stdout_stderr_drained -and $state.elapsed_seconds -le 10)
    } else {
      $processOk = [bool]($state.process -and $state.process.started -and $state.process.exit_confirmed `
        -and ($state.exit_code -is [int]) -and $state.exit_code -eq 0 -and $state.owned_process_exited `
        -and $state.owned_tree_clear -and $state.stdout_stderr_drained -and -not $state.timed_out `
        -and -not $state.memory_stop)
      $modeOk = if ($Mode -eq 'synthetic') { $state.synthetic_result_status -eq 'completed' } else { $true }
      $maxSeconds = if ($Mode -eq 'synthetic') { 180 } else { 30 }
      $state.completed = [bool]($commonOk -and $processOk -and $modeOk -and $state.elapsed_seconds -le $maxSeconds)
    }
    try { Write-Utf8NoBom -Path (Join-Path $runDir 'stdout.txt') -Text ([string]$state.stdout) } catch { $state.stdout_log_error = $_.Exception.Message; $state.completed = $false }
    try { Write-Utf8NoBom -Path (Join-Path $runDir 'stderr.txt') -Text ([string]$state.stderr) } catch { $state.stderr_log_error = $_.Exception.Message; $state.completed = $false }
    try {
      Write-Utf8NoBom -Path (Join-Path $runDir 'resource_samples.jsonl') `
        -Text (($state.resource_samples | ForEach-Object { ConvertTo-Json -InputObject $_ -Compress -Depth 8 }) -join "`n")
    } catch { $state.resource_log_error = $_.Exception.Message; $state.completed = $false }
    Write-Receipt -Path $receiptPath -Value $state
  }
  return [ordered]@{
    mode = $Mode
    run_id = $runId
    completed = [bool]$state.completed
    exit_code = $state.exit_code
    receipt_path = $receiptPath
    approval_map_sha256_before = $state.approval_map_sha256_before
    approval_map_sha256_after = $state.approval_map_sha256_after
    approval_map_unchanged = $state.approval_map_unchanged
    owned_process_exited = $state.owned_process_exited
    owned_tree_clear = $state.owned_tree_clear
    elapsed_seconds = $state.elapsed_seconds
    error = $state.error
  }
}

$result = $null
$scriptExitCode = 4
try {
  $result = Invoke-Round015
  if ($result.completed) { $scriptExitCode = 0 }
} catch {
  $result = [ordered]@{
    mode = $Mode
    completed = $false
    exit_code = $null
    error = $_.Exception.Message
    approval_map_path = 'rounds/round_015/review/approved_sources.json'
    retry_forbidden = $true
  }
}
[Console]::Out.WriteLine((ConvertTo-Json -InputObject $result -Depth 24 -Compress))
exit $scriptExitCode
