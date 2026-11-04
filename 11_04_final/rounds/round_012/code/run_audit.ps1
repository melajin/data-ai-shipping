param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('smoke','mock','audit')]
  [string]$Mode,
  [ValidateSet('1','2')]
  [string]$MockNumber = '1'
)

$ErrorActionPreference = 'Stop'
$roundDir = Split-Path -Parent $PSScriptRoot
$taskRoot = Split-Path -Parent (Split-Path -Parent $roundDir)
$mapPath = Join-Path $roundDir 'review/approved_sources.json'
$python = 'C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$tempDir = Join-Path $roundDir 'temp'
$approvedRelativePaths = @(
  'rounds/round_012/code/verify_frozen_run.py',
  'rounds/round_012/code/test_verify_frozen_run.py',
  'rounds/round_012/code/run_audit.ps1'
)

function Get-Sha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  $encoding = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Get-MapChecks($Approved) {
  $checks = @(
    foreach ($relative in $approvedRelativePaths) {
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
  return $checks
}

function Get-ProcessInventory {
  return @(
    Get-Process -Name 'python','pythonw' -ErrorAction SilentlyContinue | ForEach-Object {
      $creation = $null
      try { $creation = $_.StartTime.ToUniversalTime().ToString('o') } catch { }
      [ordered]@{ pid = [int]$_.Id; name = $_.ProcessName; creation_utc = $creation }
    }
  )
}

function Test-OwnedProcessResidual([int]$ProcessId, [string]$CreationUtc) {
  # Unknown identity is treated as a failed residual check, never as proof of absence.
  if (-not $ProcessId -or -not $CreationUtc) { return $true }
  $candidate = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $candidate) { return $false }
  try {
    $actualCreation = $candidate.StartTime.ToUniversalTime().ToString('o')
    return $actualCreation -eq $CreationUtc
  } catch {
    return $true
  }
}

function ConvertTo-WindowsCommandLineArgument([string]$Argument) {
  # ProcessStartInfo.Arguments is supported by Windows PowerShell 5.1/.NET Framework.
  # Escape according to the Windows CRT quoting rules, including embedded and trailing backslashes.
  $builder = New-Object System.Text.StringBuilder
  $backslash = [string][char]92
  [void]$builder.Append([char]34)
  $backslashCount = 0
  foreach ($character in $Argument.ToCharArray()) {
    if ([int]$character -eq 92) {
      $backslashCount++
      continue
    }
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

function Invoke-OwnedProcess(
  [string[]]$Arguments,
  [int]$WaitMilliseconds,
  [int]$CleanupMilliseconds,
  [string]$WorkingDirectory,
  [string]$ChildTempDirectory
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
  $psi.EnvironmentVariables['TMP'] = $ChildTempDirectory
  $psi.EnvironmentVariables['TEMP'] = $ChildTempDirectory

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $psi
  $started = $false
  $waitFinished = $false
  $timedOut = $false
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

  try {
    $started = $process.Start()
    if (-not $started) { throw 'Process.Start returned false' }
    $pidValue = [int]$process.Id
    $creationUtc = $process.StartTime.ToUniversalTime().ToString('o')

    # Start both drains before waiting so neither redirected pipe can fill.
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    $waitFinished = [bool]$process.WaitForExit($WaitMilliseconds)
    $timedOut = -not $waitFinished
    if (-not $waitFinished) {
      try {
        if (-not $process.HasExited) {
          $process.Kill()
          $killAttempted = $true
        }
      } catch {
        $processError = "owned process cleanup failed: $($_.Exception.Message)"
      }
      $exitConfirmed = [bool]$process.WaitForExit($CleanupMilliseconds)
    } else {
      $exitConfirmed = [bool]$process.HasExited
    }

    $remainingMilliseconds = [Math]::Max(0, $WaitMilliseconds + $CleanupMilliseconds - [int]$clock.ElapsedMilliseconds)
    if ($stdoutTask -and $stderrTask -and $remainingMilliseconds -gt 0) {
      $streamsDrained = [System.Threading.Tasks.Task]::WaitAll(
        [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask),
        [int]$remainingMilliseconds
      )
    }
    if ($streamsDrained) {
      $stdout = $stdoutTask.GetAwaiter().GetResult()
      $stderr = $stderrTask.GetAwaiter().GetResult()
    }

    $process.Refresh()
    $exitConfirmed = $exitConfirmed -or [bool]$process.HasExited
    if ($exitConfirmed) {
      $rawExitCode = $process.ExitCode
      if ($rawExitCode -is [int]) {
        $exitCode = $rawExitCode
      } else {
        $processError = 'Process exit was confirmed but ExitCode was not an Int32'
      }
    }
  } catch {
    $processError = $_.Exception.Message
    try {
      if ($started -and -not $process.HasExited) {
        $process.Kill()
        $killAttempted = $true
        $exitConfirmed = [bool]$process.WaitForExit($CleanupMilliseconds)
      }
    } catch { }
  } finally {
    $clock.Stop()
  }

  $ownedExited = $false
  if ($started) {
    try { $ownedExited = [bool]$process.HasExited } catch { }
  }
  $residual = Test-OwnedProcessResidual -ProcessId ([int]$pidValue) -CreationUtc $creationUtc
  $process.Dispose()

  return [ordered]@{
    started = $started
    pid = $pidValue
    creation_utc = $creationUtc
    wait_finished = $waitFinished
    timed_out = $timedOut
    kill_attempted = $killAttempted
    exit_confirmed = $exitConfirmed
    exit_code = $exitCode
    owned_process_exited = $ownedExited
    owned_process_residual = $residual
    stdout = $stdout
    stderr = $stderr
    stdout_stderr_drained = $streamsDrained
    elapsed_seconds = $clock.Elapsed.TotalSeconds
    wait_timeout_seconds = $WaitMilliseconds / 1000.0
    cleanup_timeout_seconds = $CleanupMilliseconds / 1000.0
    command = @($python) + $Arguments
    error = $processError
  }
}

function Read-Receipt([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-Receipt([string]$Path, $Value) {
  $json = ConvertTo-Json -InputObject $Value -Depth 20
  Write-Utf8NoBom -Path $Path -Text ($json + "`n")
}

function New-ExecutionClaim([string]$Path, $Value) {
  $json = ConvertTo-Json -InputObject $Value -Depth 8 -Compress
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
  $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
  try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

function Invoke-Round012 {
  if (-not (Test-Path -LiteralPath $mapPath -PathType Leaf)) { throw 'Missing review/approved_sources.json' }
  if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Required base Python executable is missing' }
  Set-Location -LiteralPath $taskRoot
  New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

  $approved = Get-Content -LiteralPath $mapPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($approved.schema -ne 'round012_approved_sources.v1') { throw 'Unexpected approved-source schema' }
  if (-not $approved.sha256) { throw 'Approved-source SHA map is missing' }
  $actualMapPaths = @($approved.sha256.PSObject.Properties.Name | Sort-Object)
  $expectedMapPaths = @($approvedRelativePaths | Sort-Object)
  if (($actualMapPaths -join "`n") -ne ($expectedMapPaths -join "`n")) { throw 'Approved-source map must cover exactly the three round012 code files' }
  foreach ($relative in $approvedRelativePaths) {
    $sha = [string]$approved.sha256.$relative
    if ($sha -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid SHA-256 for $relative" }
  }

  $approvalBefore = Get-Sha256 $mapPath
  $liveBefore = @(Get-MapChecks $approved)
  if (@($liveBefore | Where-Object { -not $_.match }).Count -gt 0) { throw 'Approval/live hash mismatch before launch' }

  $os = Get-CimInstance -ClassName Win32_OperatingSystem
  $availableRamGiB = [double]$os.FreePhysicalMemory / 1MB
  if ($availableRamGiB -lt 0.5) { throw "Available RAM below 0.5 GiB ($availableRamGiB); stop and recheck after other source work" }
  $otherPythonBefore = @(Get-ProcessInventory)

  $runId = switch ($Mode) {
    'smoke' { 'smoke_01' }
    'mock' { "mock_0$MockNumber" }
    'audit' { 'audit_01' }
  }
  $runDir = Join-Path $roundDir ("logs/" + $runId)
  New-Item -ItemType Directory -Force -Path $runDir | Out-Null
  $receiptPath = Join-Path $runDir 'receipt.json'
  $claimPath = Join-Path $runDir 'execution.claim'

  if ($Mode -eq 'audit') {
    if (Test-Path -LiteralPath $receiptPath) { throw 'audit_01 already has a receipt; audit retry is forbidden' }
    $passingMock = $null
    foreach ($candidateRunId in @('mock_02','mock_01')) {
      $candidate = Read-Receipt (Join-Path $roundDir ("logs/" + $candidateRunId + '/receipt.json'))
      $candidateExitIsInteger = $candidate -and ($candidate.exit_code -is [int] -or $candidate.exit_code -is [long])
      if ($candidate -and $candidate.completed -eq $true -and $candidateExitIsInteger -and $candidate.exit_code -eq 0 -and $candidate.approval_map_sha256_after -eq $approvalBefore) {
        $passingMock = $candidate
        break
      }
    }
    if (-not $passingMock) { throw 'A successful mock under this exact approval map is required before audit' }
  } elseif ($Mode -eq 'mock' -and $MockNumber -eq '2') {
    $firstPath = Join-Path $roundDir 'logs/mock_01/receipt.json'
    $first = Read-Receipt $firstPath
    if (-not $first -or $first.completed -eq $true) { throw 'mock_02 is allowed only after a failed mock_01' }
    if ($first.approval_map_sha256_after -eq $approvalBefore) { throw 'mock_02 requires a newly reviewed approval map after a source correction' }
  } elseif ($Mode -eq 'mock' -and $MockNumber -eq '1' -and (Test-Path -LiteralPath $receiptPath)) {
    throw 'mock_01 already has a receipt; duplicate execution is forbidden'
  }
  if (Test-Path -LiteralPath $claimPath) { throw "$runId claim already exists; duplicate execution is forbidden" }

  $state = [ordered]@{
    schema = 'round012_process_receipt.v1'
    mode = $Mode
    run_id = $runId
    started_utc = [DateTimeOffset]::UtcNow.ToString('o')
    completed = $false
    launched = $false
    exit_code = $null
    timed_out = $false
    timeout_seconds = if ($Mode -eq 'smoke') { 10 } else { 30 }
    available_ram_gib_before = $availableRamGiB
    expected_peak_mib = 100
    expected_peak_basis = 'standard-library JSON and a 1 MiB streaming SHA-256 buffer; no model imports'
    other_python_processes_before = $otherPythonBefore
    approval_map_path = 'rounds/round_012/review/approved_sources.json'
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
    owned_process_residual = $false
    stdout_stderr_drained = $false
    historical_round010_outcome_unchanged = $true
    error = $null
  }
  New-ExecutionClaim -Path $claimPath -Value ([ordered]@{
    schema = 'round012_execution_claim.v1'
    run_id = $runId
    mode = $Mode
    approval_map_sha256 = $approvalBefore
    claimed_utc = $state.started_utc
  })

  try {
    $sourceDir = Join-Path $runDir 'source'
    if (Test-Path -LiteralPath $sourceDir -PathType Container) {
      if (@(Get-ChildItem -LiteralPath $sourceDir -Force).Count -gt 0) { throw 'Run source snapshot directory is not empty' }
    }
    New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
    foreach ($relative in $approvedRelativePaths) {
      $livePath = Join-Path $taskRoot ($relative.Replace('/', '\'))
      $destPath = Join-Path $sourceDir ([System.IO.Path]::GetFileName($livePath))
      Copy-Item -LiteralPath $livePath -Destination $destPath
      $snapshotHash = Get-Sha256 $destPath
      $hashProperty = $approved.sha256.PSObject.Properties[$relative]
      $expectedHash = if ($hashProperty) { [string]$hashProperty.Value } else { '' }
      $state.source_snapshot[$relative] = $destPath
      $state.snapshots += [ordered]@{
        path = $relative
        snapshot_path = $destPath
        expected_sha256 = $expectedHash.ToLowerInvariant()
        snapshot_sha256 = $snapshotHash
        match = ($snapshotHash -eq $expectedHash.ToLowerInvariant())
      }
    }
    if (@($state.snapshots | Where-Object { -not $_.match }).Count -gt 0) { throw 'Copied snapshot differs from approved source' }

    if ($Mode -eq 'smoke') {
      $smokeClock = [System.Diagnostics.Stopwatch]::StartNew()
      foreach ($expectedExit in @(0,7)) {
        $remaining = [Math]::Max(0, 10000 - [int]$smokeClock.ElapsedMilliseconds)
        if ($remaining -le 0) { throw 'Smoke process-control budget exhausted before both children completed' }
        $cleanupMs = [Math]::Min(1000, [Math]::Max(0, $remaining - 1))
        $waitMs = [Math]::Min(4000, [Math]::Max(1, $remaining - $cleanupMs))
        $childCode = "import sys; print('smoke_stdout_exit_$expectedExit'); print('smoke_stderr_exit_$expectedExit', file=sys.stderr); raise SystemExit($expectedExit)"
        $child = Invoke-OwnedProcess -Arguments @('-B','-S','-c',$childCode) -WaitMilliseconds $waitMs -CleanupMilliseconds $cleanupMs -WorkingDirectory $taskRoot -ChildTempDirectory $tempDir
        $child['expected_exit_code'] = [int]$expectedExit
        $child['exit_code_matches_expected'] = (($child.exit_code -is [int]) -and ($child.exit_code -eq $expectedExit))
        $child['stdout_marker_present'] = ([string]$child.stdout).Contains("smoke_stdout_exit_$expectedExit")
        $child['stderr_marker_present'] = ([string]$child.stderr).Contains("smoke_stderr_exit_$expectedExit")
        $child['completed'] = [bool]($child.started -and $child.exit_confirmed -and $child.owned_process_exited -and -not $child.owned_process_residual -and $child.stdout_stderr_drained -and $child.exit_code_matches_expected -and $child.stdout_marker_present -and $child.stderr_marker_present -and -not $child.timed_out)
        $state.children += $child
      }
      $smokeClock.Stop()
      $state.elapsed_seconds = $smokeClock.Elapsed.TotalSeconds
      $state.stdout = (@($state.children | ForEach-Object { $_.stdout }) -join "`n")
      $state.stderr = (@($state.children | ForEach-Object { $_.stderr }) -join "`n")
      $state.owned_process_exited = (@($state.children | Where-Object { -not $_.owned_process_exited }).Count -eq 0)
      $state.owned_process_residual = (@($state.children | Where-Object { $_.owned_process_residual }).Count -gt 0)
      $state.stdout_stderr_drained = (@($state.children | Where-Object { -not $_.stdout_stderr_drained }).Count -eq 0)
      $state.exit_code = if (@($state.children | Where-Object { -not $_.completed }).Count -eq 0) { 0 } else { 4 }
      $state.launched = (@($state.children | Where-Object { $_.started }).Count -eq 2)
    } else {
      $snapshotScriptName = if ($Mode -eq 'mock') { 'test_verify_frozen_run.py' } else { 'verify_frozen_run.py' }
      $snapshotScript = Join-Path $sourceDir $snapshotScriptName
      $arguments = @('-B','-S',$snapshotScript)
      if ($Mode -eq 'audit') {
        $arguments += @('--source-round','round_010','--output','rounds/round_012/artifacts/provenance_audit.json','--root',$taskRoot)
      }
      $state.process = Invoke-OwnedProcess -Arguments $arguments -WaitMilliseconds 28000 -CleanupMilliseconds 2000 -WorkingDirectory $taskRoot -ChildTempDirectory $tempDir
      $state.launched = [bool]$state.process.started
      $state.exit_code = $state.process.exit_code
      $state.timed_out = [bool]$state.process.timed_out
      $state.elapsed_seconds = $state.process.elapsed_seconds
      $state.stdout = $state.process.stdout
      $state.stderr = $state.process.stderr
      $state.owned_process_exited = [bool]$state.process.owned_process_exited
      $state.owned_process_residual = [bool]$state.process.owned_process_residual
      $state.stdout_stderr_drained = [bool]$state.process.stdout_stderr_drained
    }
  } catch {
    $state.error = $_.Exception.Message
  } finally {
    $state.finished_utc = [DateTimeOffset]::UtcNow.ToString('o')
    try { $state.live_postcheck = @(Get-MapChecks $approved) } catch { $state.live_postcheck_error = $_.Exception.Message }
    try { $state.approval_map_sha256_after = Get-Sha256 $mapPath } catch { $state.approval_map_postcheck_error = $_.Exception.Message }
    $state.approval_map_unchanged = [bool]($state.approval_map_sha256_before -and $state.approval_map_sha256_after -and $state.approval_map_sha256_before -eq $state.approval_map_sha256_after)
    $state.snapshot_postcheck = @(
      foreach ($snapshot in $state.snapshots) {
        $current = if (Test-Path -LiteralPath $snapshot.snapshot_path -PathType Leaf) { Get-Sha256 $snapshot.snapshot_path } else { $null }
        [ordered]@{ path = $snapshot.path; snapshot_sha256 = $current; match = [bool]($current -and $current -eq $snapshot.expected_sha256) }
      }
    )
    $state.other_python_processes_after = @(Get-ProcessInventory)

    $liveOk = @($state.live_postcheck).Count -eq $approvedRelativePaths.Count -and @($state.live_postcheck | Where-Object { -not $_.match }).Count -eq 0
    $snapshotOk = @($state.snapshots).Count -eq $approvedRelativePaths.Count -and @($state.snapshots | Where-Object { -not $_.match }).Count -eq 0 -and @($state.snapshot_postcheck).Count -eq $approvedRelativePaths.Count -and @($state.snapshot_postcheck | Where-Object { -not $_.match }).Count -eq 0
    $commonOk = [bool]($state.launched -and $state.approval_map_unchanged -and $liveOk -and $snapshotOk)
    if ($Mode -eq 'smoke') {
      $childrenOk = @($state.children).Count -eq 2 -and @($state.children | Where-Object { -not $_.completed }).Count -eq 0
      $state.completed = [bool]($commonOk -and $childrenOk -and $state.elapsed_seconds -le 10)
    } else {
      $processOk = [bool]($state.process -and $state.process.started -and $state.process.exit_confirmed -and ($state.exit_code -is [int]) -and $state.exit_code -eq 0 -and $state.owned_process_exited -and -not $state.owned_process_residual -and $state.stdout_stderr_drained -and -not $state.timed_out)
      $state.completed = [bool]($commonOk -and $processOk)
    }
    try { Write-Utf8NoBom -Path (Join-Path $runDir 'stdout.txt') -Text ([string]$state.stdout) } catch { $state.stdout_log_error = $_.Exception.Message; $state.completed = $false }
    try { Write-Utf8NoBom -Path (Join-Path $runDir 'stderr.txt') -Text ([string]$state.stderr) } catch { $state.stderr_log_error = $_.Exception.Message; $state.completed = $false }
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
    owned_process_residual = $state.owned_process_residual
    elapsed_seconds = $state.elapsed_seconds
    error = $state.error
  }
}

$result = $null
$scriptExitCode = 4
try {
  $result = Invoke-Round012
  if ($result.completed) { $scriptExitCode = 0 }
} catch {
  $result = [ordered]@{
    mode = $Mode
    completed = $false
    exit_code = $null
    error = $_.Exception.Message
    approval_map_path = 'rounds/round_012/review/approved_sources.json'
    historical_round010_outcome_unchanged = $true
  }
}
[Console]::Out.WriteLine((ConvertTo-Json -InputObject $result -Depth 20 -Compress))
exit $scriptExitCode
