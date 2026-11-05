[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$recoveryRoot = Join-Path $PSScriptRoot 'recovery'
New-Item -ItemType Directory -Path $recoveryRoot -Force | Out-Null
$tempRoot = Join-Path $recoveryRoot 'tmp'
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$receiptPath = Join-Path $recoveryRoot '20261105_capture_working_set_recovery.json'
if (Test-Path -LiteralPath $receiptPath) { throw 'Recovery already recorded; inspect it instead of repeating.' }
$started = [DateTime]::UtcNow.ToString('o')
$initialMemory = Get-CimInstance Win32_OperatingSystem
$initialAvailable = $initialMemory.FreePhysicalMemory / 1MB
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CaptureMemoryRecovery {
 [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
 [DllImport("psapi.dll", SetLastError=true)] public static extern bool EmptyWorkingSet(IntPtr process);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
}
'@
[uint32]$foregroundProcessId = 0
[void][CaptureMemoryRecovery]::GetWindowThreadProcessId([CaptureMemoryRecovery]::GetForegroundWindow(), [ref]$foregroundProcessId)
$candidates = @(Get-Process -Name SnippingTool -ErrorAction SilentlyContinue)
if ($candidates.Count -gt 64) { throw 'Unexpected process count; inspect before broadening scope.' }
$records = @()
foreach ($capture in $candidates) {
    $capture.Refresh()
    $before = $capture.WorkingSet64
    $record = [ordered]@{pid=$capture.Id; path=$capture.Path; before_rss_bytes=$before; action='skipped'; reason=$null}
    if ($capture.MainWindowHandle -ne 0 -or $capture.Id -eq $foregroundProcessId) {
        $record.reason = 'Visible or foreground instance retained'
    } elseif ($capture.Path -notmatch '^C:\\Program Files\\WindowsApps\\Microsoft\.ScreenSketch_[^\\]+\\SnippingTool\\SnippingTool\.exe$') {
        $record.reason = 'Executable path outside observed Microsoft capture package'
    } else {
        $processHandle = [CaptureMemoryRecovery]::OpenProcess(0x1100, $false, [uint32]$capture.Id)
        if ($processHandle -eq [IntPtr]::Zero) {
            $record.reason = 'OpenProcess failed: ' + [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        } else {
            try {
                if ([CaptureMemoryRecovery]::EmptyWorkingSet($processHandle)) {
                    $record.action = 'working_set_trimmed_once'
                } else {
                    $record.reason = 'EmptyWorkingSet failed: ' + [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                }
            } finally { [void][CaptureMemoryRecovery]::CloseHandle($processHandle) }
        }
    }
    try { $capture.Refresh(); $record.after_rss_bytes=$capture.WorkingSet64 } catch { $record.after_rss_bytes=$null }
    $records += [pscustomobject]$record
}
$finalMemory = Get-CimInstance Win32_OperatingSystem
$result = [ordered]@{
    started_utc=$started; finished_utc=[DateTime]::UtcNow.ToString('o')
    authorization='User explicitly requested RAM recovery and experiment resumption'
    method='One-pass EmptyWorkingSet on path-verified background SnippingTool only'
    documentation='https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-emptyworkingset'
    expected_helper_peak_gib=0.1; estimate_basis='Small PowerShell/PInvoke helper, metadata and 44 process handles; no dataset or model load'
    foreground_pid_excluded=$foregroundProcessId; observed_instances=$candidates.Count
    successful_trims=@($records | Where-Object {$_.action -eq 'working_set_trimmed_once'}).Count
    processes_terminated=0; initial_available_gib=$initialAvailable
    final_available_gib=$finalMemory.FreePhysicalMemory/1MB
    available_ram_is_not_reserved=$true
    note='Working-set pages may return when apps are used. Process virtual state and private allocation are retained. No monitor or repeated trimming loop.'
    records=$records
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
[pscustomobject]$result | Select-Object started_utc,finished_utc,observed_instances,successful_trims,processes_terminated,initial_available_gib,final_available_gib | ConvertTo-Json
