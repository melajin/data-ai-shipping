[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^round_[0-9]{3,}$')]
    [string]$FromRound,
    [switch]$InspectOnly
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $taskRoot
$handoffPath = Join-Path $taskRoot 'NEXT_SESSION.md'
$statusPath = Join-Path $taskRoot 'STATUS.json'
$receiptDirectory = Join-Path $PSScriptRoot 'receipts'
$receiptPath = Join-Path $receiptDirectory ($FromRound + '_launch.json')
$claimPath = Join-Path $receiptDirectory ($FromRound + '_launch.claim')
$stdoutPath = Join-Path $receiptDirectory ($FromRound + '_launch.stdout.json')
$stderrPath = Join-Path $receiptDirectory ($FromRound + '_launch.stderr.txt')
$handoffSnapshotPath = Join-Path $receiptDirectory ($FromRound + '_NEXT_SESSION.md')
$statusSnapshotPath = Join-Path $receiptDirectory ($FromRound + '_STATUS.json')
$cliPath = if ($env:ORCA_CLI_COMMAND) { $env:ORCA_CLI_COMMAND } else { 'C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe' }

foreach ($required in @($handoffPath, $statusPath, (Join-Path $taskRoot 'AGENTS.md'), (Join-Path $taskRoot 'CYCLE_PROTOCOL.md'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required handoff file missing: $required" }
}
$status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
$roundReport = Join-Path $taskRoot ("rounds\$FromRound\ROUND_REPORT.md")
$handoffHash = (Get-FileHash -LiteralPath $handoffPath -Algorithm SHA256).Hash
$launchPrompt = @"
사용자가 승인한 새 회차 관리자 세션입니다. 모델은 gpt-6.1-sol, effort high로 요청되었습니다. 먼저 작업 디렉터리를 아래 루트로 설정하고 해당 루트의 AGENTS.md, STATUS.json, CYCLE_PROTOCOL.md, NEXT_SESSION.md, 직전 회차 결과 보고서를 읽으세요.

작업 루트: $taskRoot
원자료 읽기 전용: F:\문제 데이터_수정_1027
이전 코드/결과 읽기 전용: D:\repos\fishing-track-classification
인계 출발 회차: $FromRound
인계 문서: $handoffPath
이 인계의 보존 사본: $handoffSnapshotPath
전달 당시 인계 문서 SHA256: $handoffHash

목표: 선박 조업 분류 micro-F1 0.7 이상을 추구하며 회차별 결과 문서 저장 → 구체적인 다음 작업 작성 → 새로운 GPT-6.1 Sol high 세션에서 다음 회차 실행을 반복합니다. 이 모델 요청을 실제 모델 검증이라고 과장하지 말고, 실행 환경이 제공하는 모델/effort 증거를 남기세요. 보조 에이전트는 gpt-6-luna / xhigh만, 사용자 상한 최대 4명이며 호스트 동시성 제한을 우선합니다. 모델을 바꾸지 말고 별도 코드 작성 담당/검토 담당을 두세요. 모든 출력은 작업 루트 아래에 저장하며 원자료와 이전 저장소를 수정하지 마세요. 학습·국소 실험·인계는 사용자에게 반복 승인을 받을 필요 없이 허용되어 있습니다.

현재 이미 다른 관리자가 같은 회차를 실행 중인 증거가 있으면 중복 실행하지 말고 인계 영수증을 확인하세요. 이 실행은 새로운 관리자이므로 직전 관리자는 같은 실험을 계속 수행하지 않습니다. 개발 OUTER 5897척은 반복 노출됐습니다. 독립 평가·공식 제출·개발 점수를 구분하고 holdout 이력 확인 없이 읽지 마세요. 공식 제출·외부 업로드·유료 자원 신규 사용은 기본 범위에서 제외합니다.

NEXT_SESSION.md의 작업을 실제로 수행하고 결과를 저장하세요. 각 회차는 실행 전 정한 유한 실험 수/자원 범위를 지키고, 완료 시 rounds/round_NNN/ROUND_REPORT.md, STATUS.json, EXPERIMENT_LEDGER.csv, NEXT_SESSION.md를 갱신하세요. STATUS의 current_round는 이번 완료 회차로 남기고 handoff.ready=true로 설정하세요. 동일한 실패/무정보 실험을 무한 반복하지 말고 원인과 다음 가설을 변경하세요. 목표 미달이고 다음 작업이 실행 가능하면 다음 명령으로 fresh manager에게 인계하고 수락 영수증을 확인한 뒤 이 세션은 종료하세요:
& '$PSScriptRoot\Start-NextSession.ps1' -FromRound '<이번 완료 회차 round_NNN>'
기술적으로 실행할 수 없는 외부 제약이나 사용자 중지가 있으면 이유와 정확한 재개 방법을 남기세요. 점수 0.7 달성을 보장하거나 측정하지 않은 성능을 만들지 마세요.
"@

if ($InspectOnly) {
    [ordered]@{
        mode = 'inspect_only_no_launch'; from_round = $FromRound; task_root = $taskRoot
        workspace = "path:$workspaceRoot"; model = 'gpt-6.1-sol'; effort = 'high'
        handoff_sha256 = $handoffHash; receipt_path = $receiptPath
        existing_receipt = (Test-Path -LiteralPath $receiptPath)
        existing_claim = (Test-Path -LiteralPath $claimPath)
        prompt = $launchPrompt
    } | ConvertTo-Json -Depth 6
    return
}

New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
if (Test-Path -LiteralPath $receiptPath) {
    $previous = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($previous.accepted -eq $true) {
        Write-Output (Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8)
        return
    }
    throw "A previous uncertain/failed launch exists at $receiptPath. Inspect its operationId and live session before recovery; do not launch again blindly."
}
if ($status.current_round -ne $FromRound) { throw "FromRound does not match STATUS.current_round. Inspect the current handoff before launching." }
if ($status.handoff.ready -ne $true) { throw "The manager has not marked handoff.ready=true. Finish and save the round before launching." }
if (-not (Test-Path -LiteralPath $roundReport -PathType Leaf)) { throw "Completed round report is missing: $roundReport" }

# CreateNew makes concurrent duplicate submissions fail before calling Orca.
$claimStream = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
$claimText = [Text.Encoding]::UTF8.GetBytes("$([DateTime]::UtcNow.ToString('o'))`n$handoffHash`n")
$claimStream.Write($claimText, 0, $claimText.Length)
$claimStream.Dispose()
Copy-Item -LiteralPath $handoffPath -Destination $handoffSnapshotPath
Copy-Item -LiteralPath $statusPath -Destination $statusSnapshotPath
if ((Get-FileHash -LiteralPath $handoffSnapshotPath -Algorithm SHA256).Hash -ne $handoffHash) {
    throw 'NEXT_SESSION changed while preparing launch. Inspect the claim and snapshots before recovery; no agent was launched.'
}
$startedAt = [DateTime]::UtcNow.ToString('o')
$receipt = [ordered]@{
    from_round = $FromRound; requested_model = 'gpt-6.1-sol'; requested_effort = 'high'
    task_root = $taskRoot; workspace = "path:$workspaceRoot"; handoff_sha256 = $handoffHash
    started_at_utc = $startedAt; accepted = $false; status = 'unknown'; exit_code = $null
    raw_stdout = $stdoutPath; raw_stderr = $stderrPath; host_response = $null
    handoff_snapshot = $handoffSnapshotPath; status_snapshot = $statusSnapshotPath
}
try {
    $rawOutput = (& $cliPath agent launch --agent codex --worktree "path:$workspaceRoot" --model gpt-6.1-sol --effort high --prompt $launchPrompt --json 2> $stderrPath | Out-String)
    $receipt.exit_code = $LASTEXITCODE
    [IO.File]::WriteAllText($stdoutPath, $rawOutput, (New-Object Text.UTF8Encoding($false)))
    $response = $rawOutput | ConvertFrom-Json
    $receipt.host_response = $response
    $launch = if ($response.result.launch) { $response.result.launch } else { $response.result }
    $promptOutcome = $launch.prompt.outcome
    $accepted = ($response.ok -eq $true) -and ($promptOutcome -in @('journaled', 'handed-to-terminal'))
    $receipt.accepted = $accepted
    $receipt.status = if ($accepted) { 'prompt_delivered' } else { 'requires_inspection' }
    $receipt.completed_at_utc = [DateTime]::UtcNow.ToString('o')
    $receipt | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    $receipt | ConvertTo-Json -Depth 30
    if (-not $accepted) { throw "Orca did not provide a confirmed prompt delivery. Inspect $receiptPath and do not blindly repeat this launch." }
} catch {
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        $receipt.error = $_.Exception.Message
        $receipt.completed_at_utc = [DateTime]::UtcNow.ToString('o')
        $receipt | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    }
    throw
}
