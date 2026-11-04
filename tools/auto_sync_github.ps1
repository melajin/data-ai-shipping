# =====================================================================
# DATA AI SHIPPING - Automated GitHub Synchronization Script
# Runs every 30 minutes to detect and commit new/modified files.
# =====================================================================

$WorkspaceDir = "D:\obsidian\claude\obsidian_export\DATA AI SHIPPING"
$LogFile = Join-Path $WorkspaceDir "tools\auto_sync.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Output $line
}

try {
    Set-Location -LiteralPath $WorkspaceDir
    git config core.quotepath false

    Write-Log "=== Starting 30-minute GitHub sync check ==="

    # 1. Check for working tree status
    $statusOutput = git status --porcelain
    if (-not $statusOutput) {
        Write-Log "No changes detected. Working tree is clean."
        exit 0
    }

    Write-Log "Changes detected. Evaluating changed files..."

    # 2. Stage changes (respecting .gitignore)
    git add -A

    # 3. Safeguard: Unstage any file that exceeds 95MB to prevent GitHub rejection
    $stagedFiles = git diff --cached --name-only
    $largeFilesCount = 0

    foreach ($file in $stagedFiles) {
        if (Test-Path -LiteralPath $file) {
            $item = Get-Item -LiteralPath $file
            if ($item.Length -gt 95MB) {
                $sizeMB = [math]::Round($item.Length / 1MB, 2)
                Write-Log "WARNING: Unstaging large file exceeding 95MB limit: $file ($sizeMB MB)"
                git reset -q HEAD -- "$file"
                $largeFilesCount++
            }
        }
    }

    # 4. Check if there are still staged files to commit
    $remainingStaged = git diff --cached --name-only
    if (-not $remainingStaged) {
        Write-Log "No valid files to commit after large file filtering."
        exit 0
    }

    $stagedCount = ($remainingStaged | Measure-Object).Count
    Write-Log "Staged $stagedCount files for commit."

    # 5. Commit
    $nowStr = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $commitMsg = "auto: periodic sync $nowStr"
    $commitOutput = git commit -m "$commitMsg" 2>&1
    Write-Log "Committed with message: '$commitMsg'"

    # 6. Push to GitHub
    Write-Log "Pushing to GitHub (origin main)..."
    $pushOutput = git push origin main 2>&1
    Write-Log "Push result: $pushOutput"
    Write-Log "Sync completed successfully."

} catch {
    Write-Log "ERROR: An exception occurred during sync: $($_.Exception.Message)"
    exit 1
}
