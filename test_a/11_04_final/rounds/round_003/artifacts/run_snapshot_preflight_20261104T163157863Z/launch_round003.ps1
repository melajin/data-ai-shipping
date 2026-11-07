[CmdletBinding()]
param(
    [ValidateSet('preflight', 'score')]
    [string]$Mode = 'preflight',
    [string]$ManagerGo = ''
)

$roundRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $roundRoot '..\..')).Path
$python = Join-Path $projectRoot 'environments\round_002_catboost\Scripts\python.exe'
$runner = Join-Path $PSScriptRoot 'run_round003.py'
$config = Join-Path $roundRoot 'configs\experiment.json'
$logs = Join-Path $roundRoot 'logs'
$cache = Join-Path $logs 'pycache'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Round002 Python environment is unavailable: $python"
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Round003 runner is unavailable: $runner"
}
if ($Mode -eq 'score' -and [string]::IsNullOrWhiteSpace($ManagerGo)) {
    throw 'Score mode requires the manager authorization text supplied after reviewer precheck.'
}

New-Item -ItemType Directory -Force -Path $logs, $cache | Out-Null
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$stdout = Join-Path $logs "stdout_${Mode}_${stamp}.log"
$stderr = Join-Path $logs "stderr_${Mode}_${stamp}.log"
$manifestPath = Join-Path $logs "launch_manifest_${Mode}_${stamp}.json"
$receiptPath = Join-Path $logs "launch_receipt_${Mode}_${stamp}.json"
$snapshots = Join-Path $roundRoot "artifacts\run_snapshot_${Mode}_${stamp}"
$started = [DateTimeOffset]::UtcNow

$active = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains('run_round003.py') }
if ($active) {
    throw "A round003 runner process is already active; refusing duplicate launch. PID(s): $($active.ProcessId -join ',')"
}

# Snapshot the exact launch sources and frozen files before creating the process.
New-Item -ItemType Directory -Force -Path $snapshots | Out-Null
$snapshotFiles = [ordered]@{
    runner = @{ source = $runner; snapshot = (Join-Path $snapshots 'run_round003.py') }
    launcher = @{ source = $PSCommandPath; snapshot = (Join-Path $snapshots 'launch_round003.ps1') }
    config = @{ source = $config; snapshot = (Join-Path $snapshots 'experiment.json') }
    plan = @{ source = (Join-Path $roundRoot 'ROUND_PLAN.md'); snapshot = (Join-Path $snapshots 'ROUND_PLAN.md') }
}
$launchHashes = [ordered]@{}
foreach ($name in $snapshotFiles.Keys) {
    Copy-Item -LiteralPath $snapshotFiles[$name].source -Destination $snapshotFiles[$name].snapshot -Force
    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotFiles[$name].source).Hash.ToLowerInvariant()
    $snapshotHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotFiles[$name].snapshot).Hash.ToLowerInvariant()
    if ($sourceHash -ne $snapshotHash) { throw "Launch snapshot hash mismatch for $name" }
    $launchHashes[$name] = [ordered]@{ source = $snapshotFiles[$name].source; snapshot = $snapshotFiles[$name].snapshot;
        source_sha256 = $sourceHash; snapshot_sha256 = $snapshotHash }
}
$configObject = Get-Content -Raw -Encoding UTF8 -LiteralPath $config | ConvertFrom-Json
$osMemory = Get-CimInstance Win32_OperatingSystem
$freeRamGiB = [double]$osMemory.FreePhysicalMemory * 1KB / 1GB
if ($Mode -eq 'score' -and $freeRamGiB -lt 1.5) {
    throw ("Scoring blocked: available RAM is {0:N3} GiB, below the frozen 1.5 GiB minimum." -f $freeRamGiB)
}
$computeLimitMs = [int]$configObject.budget.compute_minutes * 60 * 1000
$managerDeadline = [DateTimeOffset]::Parse([string]$configObject.budget.manager_deadline_utc).ToUniversalTime()
$managerRemainingMs = [int]($managerDeadline - [DateTimeOffset]::UtcNow).TotalMilliseconds
$timeoutMs = [Math]::Min($computeLimitMs, $managerRemainingMs)
if ($timeoutMs -le 0) { throw 'Manager deadline or compute budget has already expired.' }
$launchManifest = [ordered]@{
    mode = $Mode
    frozen_before_process_start = $true
    created_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    round_root = $roundRoot
    python = $python
    sources = $launchHashes
    compute_budget_minutes = [int]$configObject.budget.compute_minutes
    manager_deadline_utc = $managerDeadline.ToString('o')
    process_timeout_ms = $timeoutMs
    free_ram_gib_at_launch = $freeRamGiB
    minimum_free_ram_gib_for_score = 1.5
    command_template = 'python run_round003.py --mode {mode} --config {config}'
    stdout = $stdout
    stderr = $stderr
    pycache_directory = $cache
    temp_directory = $logs
    thread_cap = 3
}
$launchManifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $manifestPath

# Keep bytecode and temporary files inside the round workspace; cap library threads at three.
$env:PYTHONPYCACHEPREFIX = $cache
$env:TEMP = $logs
$env:TMP = $logs
$env:TMPDIR = $logs
$env:OMP_NUM_THREADS = '3'
$env:MKL_NUM_THREADS = '3'
$env:OPENBLAS_NUM_THREADS = '3'
$env:NUMEXPR_NUM_THREADS = '3'
$env:BLIS_NUM_THREADS = '3'
if ($Mode -eq 'score') {
    $env:ROUND003_MANAGER_GO = $ManagerGo
}

$escapedRunner = '"' + $runner.Replace('"', '\"') + '"'
$escapedConfig = '"' + $config.Replace('"', '\"') + '"'
$arguments = "$escapedRunner --mode $Mode --config $escapedConfig"
if ($Mode -eq 'score') {
    $escapedGo = '"' + $ManagerGo.Replace('"', '\"') + '"'
    $arguments += " --manager-go $escapedGo"
}
$command = '"' + $python + '" ' + $arguments
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $roundRoot `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
$finishedWithinBudget = $process.WaitForExit($timeoutMs)
$timedOut = -not $finishedWithinBudget
if ($timedOut) {
    # Stop only the process created by this wrapper; do not touch other user processes.
    $process.Kill()
    $process.WaitForExit()
}
$process.Refresh()
$finished = [DateTimeOffset]::UtcNow
$exitCode = [int]$process.ExitCode

$receipt = [ordered]@{
    mode = $Mode
    status = if ($exitCode -eq 0 -and -not $timedOut) { 'completed' } elseif ($timedOut) { 'timed_out_and_stopped_owned_runner' } else { 'failed' }
    started_at_utc = $started.ToString('o')
    finished_at_utc = $finished.ToString('o')
    elapsed_seconds = ($finished - $started).TotalSeconds
    launcher_pid = $PID
    runner_pid = $process.Id
    exit_code = $exitCode
    python = $python
    runner = $runner
    runner_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $runner).Hash.ToLowerInvariant()
    config = $config
    config_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $config).Hash.ToLowerInvariant()
    working_directory = $roundRoot
    command = $command
    launch_manifest = $manifestPath
    launch_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
    stdout = $stdout
    stderr = $stderr
    pycache_directory = $cache
    temp_directory = $logs
    thread_cap = 3
    manager_go_supplied = ($Mode -eq 'score')
    timed_out = $timedOut
    source_hashes_still_match_launch = [ordered]@{
        runner = ((Get-FileHash -Algorithm SHA256 -LiteralPath $runner).Hash.ToLowerInvariant() -eq $launchHashes.runner.source_sha256)
        config = ((Get-FileHash -Algorithm SHA256 -LiteralPath $config).Hash.ToLowerInvariant() -eq $launchHashes.config.source_sha256)
    }
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath $receiptPath
Write-Output ($receipt | ConvertTo-Json -Depth 6)
Write-Output "launch_receipt=$receiptPath"
if ($exitCode -ne 0) { exit $exitCode }
