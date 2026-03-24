#requires -version 3.0
<#
.SYNOPSIS
    Hash Checker - Calculates MD5 and SHA256 hashes of a file
.DESCRIPTION
    Compatible with PowerShell 3.0+ (Windows 7 SP1+, Windows Server 2008 R2+)
.PARAMETER FilePath
    Path to the file to be hashed
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$FilePath
)

# Wrap everything in try-catch to prevent silent crashes
try {

# Set console encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Create debug log
$logFile = Join-Path -Path $env:TEMP -ChildPath "hash_checker_debug.log"
$logContent = @"
========================================
Hash Checker Debug Log
$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
========================================

Received FilePath parameter: '$FilePath'
FilePath Length: $($FilePath.Length)
FilePath Type: $($FilePath.GetType().FullName)

Checking existence with Test-Path...
Result: $(Test-Path -Path $FilePath)

Checking as literal path...
Literal Result: $(Test-Path -LiteralPath $FilePath)

File after trimming quotes: '$($FilePath.Trim('"'))'
Test after trim: $(Test-Path -LiteralPath $FilePath.Trim('"'))

========================================
"@

$logContent | Out-File -FilePath $logFile -Encoding UTF8 -Force

# Clear screen
Clear-Host

Write-Host "Debug log created at: $logFile"
Write-Host ""

# Try to clean the path
$FilePath = $FilePath.Trim()
$FilePath = $FilePath.Trim('"')

# Check if file exists
if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
    Write-Host ""
    Write-Host "========================================================"
    Write-Host "  ERROR"
    Write-Host "========================================================"
    Write-Host ""
    Write-Host "  File not found:"
    Write-Host "  $FilePath"
    Write-Host ""
    Write-Host "  Debug log saved at:"
    Write-Host "  $logFile"
    Write-Host ""
    Write-Host "========================================================"
    Write-Host ""
    Read-Host "Press ENTER to close"
    exit 1
}

# Get file info
try {
    "Getting file info..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $file = Get-Item -LiteralPath $FilePath
    $fileName = $file.Name
    $filePath = $file.DirectoryName
    $fileSize = $file.Length
    
    "File info retrieved successfully" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "FileName: $fileName" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "FilePath: $filePath" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "FileSize: $fileSize" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    # Add success to log
    "File found successfully!" | Out-File -FilePath $logFile -Encoding UTF8 -Append
}
catch {
    "Error getting file info: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    Write-Host "Error: $($_.Exception.Message)"
    Write-Host ""
    Read-Host "Press ENTER to close"
    exit 1
}

Write-Host ""
Write-Host "========================================================"
Write-Host "  HASH CHECKER - MD5 and SHA256"
Write-Host "========================================================"
Write-Host ""
Write-Host "File: $fileName"
Write-Host "Path: $filePath\"
Write-Host "Size: $fileSize bytes"
Write-Host ""
Write-Host "--------------------------------------------------------"
Write-Host "Calculating hashes... Please wait."
Write-Host "--------------------------------------------------------"
Write-Host ""

"Starting hash calculations..." | Out-File -FilePath $logFile -Encoding UTF8 -Append

$md5Hash = "Not calculated"
$sha256Hash = "Not calculated"

# Calculate MD5
Write-Host "[1/2] Calculating MD5..."
try {
    "Starting MD5 calculation..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $stream = [System.IO.File]::OpenRead($file.FullName)
    
    "MD5 stream opened, computing..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $hashBytes = $md5.ComputeHash($stream)
    $stream.Close()
    $stream.Dispose()
    $md5.Dispose()
    
    $md5Hash = [System.BitConverter]::ToString($hashBytes) -replace '-',''
    
    "MD5 success: $md5Hash" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    Write-Host "     [OK] $md5Hash"
}
catch {
    $errorMsg = $_.Exception.Message
    Write-Host "     [ERROR] Could not calculate MD5: $errorMsg"
    "MD5 Error: $errorMsg" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "MD5 StackTrace: $($_.Exception.StackTrace)" | Out-File -FilePath $logFile -Encoding UTF8 -Append
}

Write-Host ""

# Calculate SHA256
Write-Host "[2/2] Calculating SHA256..."
if ($fileSize -gt 1GB) {
    Write-Host "     (This may take several minutes for large files...)"
}

try {
    "Starting SHA256 calculation..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    
    "SHA256 object created, opening file stream..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $stream = [System.IO.File]::OpenRead($file.FullName)
    
    "File stream opened, computing hash..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $hashBytes = $sha256.ComputeHash($stream)
    
    "Hash computed, closing stream..." | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    $stream.Close()
    $stream.Dispose()
    $sha256.Dispose()
    
    $sha256Hash = [System.BitConverter]::ToString($hashBytes) -replace '-',''
    
    "SHA256 success: $sha256Hash" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    Write-Host "     [OK] $sha256Hash"
}
catch {
    $errorMsg = $_.Exception.Message
    Write-Host "     [ERROR] Could not calculate SHA256: $errorMsg"
    "SHA256 Error: $errorMsg" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "SHA256 StackTrace: $($_.Exception.StackTrace)" | Out-File -FilePath $logFile -Encoding UTF8 -Append
}

Write-Host ""
Write-Host "========================================================"
Write-Host "  VERIFICATION COMPLETED"
Write-Host "========================================================"
Write-Host ""

# Save results to file
$outputFile = Join-Path -Path $filePath -ChildPath "$($file.BaseName)_HASHES.txt"

$outputContent = @"
========================================================
  FILE HASHES
========================================================

File: $fileName
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Size: $fileSize bytes
Full path: $($file.FullName)

--------------------------------------------------------
MD5:    $md5Hash
SHA256: $sha256Hash
--------------------------------------------------------

Verified on: $env:COMPUTERNAME

========================================================
"@

try {
    [System.IO.File]::WriteAllText($outputFile, $outputContent, [System.Text.Encoding]::UTF8)
    Write-Host "Result saved to:"
    Write-Host $outputFile
}
catch {
    Write-Host "[WARNING] Could not save result file: $($_.Exception.Message)"
    "Save file error: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding UTF8 -Append
}

Write-Host ""
Write-Host "========================================================"
Write-Host ""
Read-Host "Press ENTER to close"

} catch {
    # Global exception handler
    $globalError = $_.Exception.Message
    $globalStack = $_.Exception.StackTrace
    
    "`n`nGLOBAL EXCEPTION CAUGHT:" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "Error: $globalError" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    "StackTrace: $globalStack" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    
    Write-Host ""
    Write-Host "========================================================"
    Write-Host "  CRITICAL ERROR"
    Write-Host "========================================================"
    Write-Host ""
    Write-Host "An unexpected error occurred:"
    Write-Host $globalError
    Write-Host ""
    Write-Host "Full details saved to: $logFile"
    Write-Host ""
    Write-Host "========================================================"
    Write-Host ""
    Read-Host "Press ENTER to close"
    exit 1
}