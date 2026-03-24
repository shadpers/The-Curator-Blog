param (
    [Parameter(Mandatory=$true, Position=0)]
    [Alias("Arquivo")]
    [string]$File
)

# Trim quotes if present
$File = $File.Trim('"').Trim("'")

# Validate if the file exists using LiteralPath
if (-not (Test-Path -LiteralPath $File)) {
    Write-Error "File not found or invalid path: $File"
    Write-Host "Tried path: $File" -ForegroundColor Yellow
    exit 1
}

# Get the folder where the PS1 script is
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# File information (get first to ensure file is accessible)
try {
    $info = Get-Item -LiteralPath $File -ErrorAction Stop
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $File -ErrorAction Stop
} catch {
    Write-Error "Cannot access file: $_"
    exit 1
}

# Report path (includes scanned file name at the beginning)
$FileNameNoExt = [IO.Path]::GetFileNameWithoutExtension($info.Name)
# Remove invalid filename characters from report name
$FileNameNoExt = $FileNameNoExt -replace '[\\/:*?"<>|]', '_'
$ReportPath = Join-Path $ScriptDir ("{0}_DefenderScan_{1}.txt" -f $FileNameNoExt,(Get-Date -Format yyyyMMdd_HHmmss))

# Start custom scan
$start = Get-Date
try {
    Start-MpScan -ScanType CustomScan -ScanPath $File -ErrorAction Stop
    Start-Sleep -Seconds 10
} catch {
    Write-Warning "Scan may have failed: $_"
}
$end = Get-Date
$duration = $end - $start

# Defender status
$status = Get-MpComputerStatus

# Collect only detections related to the scanned file
$threats = Get-MpThreatDetection | Where-Object { $_.Resources -match [Regex]::Escape($File) }

# Build report content
$ReportContent = @"
==== Microsoft Defender Scan Report ====
Date/Time: $end
Scanned File: $File

--- File Information ---
Name: $($info.Name)
Size: $([math]::Round($info.Length/1KB,2)) KB
Last Modified: $($info.LastWriteTime)
SHA256: $($hash.Hash)

--- Engine & Definitions ---
Engine Version: $($status.AMEngineVersion)
Antivirus DB Version: $($status.AntivirusSignatureVersion)
Antispyware DB Version: $($status.AntispywareSignatureVersion)
Last Update: $($status.AntivirusSignatureLastUpdated)

--- Real-time Protection ---
Enabled: $($status.RealTimeProtectionEnabled)
Tamper Protection: $($status.IsTamperProtected)
Cloud Protection: $($status.IsCloudProtectionEnabled)
Automatic Sample Submission: $($status.IsBehaviorMonitorEnabled)

--- Scan Results ---
Duration: $([math]::Round($duration.TotalSeconds,2)) seconds
Threats Found: $($threats.Count)

$(
    if ($threats) {
        $threats | Format-List | Out-String
    } else {
        "No threats detected."
    }
)
"@

# Save report
$ReportContent | Out-File -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Report generated at: $ReportPath" -ForegroundColor Green