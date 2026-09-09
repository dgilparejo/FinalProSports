<#
.SYNOPSIS
  Rotate the password of the encrypted custody archive (_custodia_tfm_originales.7z). No password is ever printed,
  logged or written in clear text by this script.

.DESCRIPTION
  Two modes.

  INTERACTIVE (default): 7-Zip asks for the OLD password (extraction) and for the NEW one (compression and test)
  through its own prompt (-p with no value: no echo). Run it yourself in a console.

  NON-INTERACTIVE (-OldPasswordFile and -NewPasswordDpapiFile given): the old password is read from a text file (the
  compromised one) without being displayed; the new one is generated with the Windows cryptographic RNG (32 chars,
  ~190 bits), passed to 7-Zip in-process and stored ONLY as a DPAPI-protected SecureString bound to the current
  Windows account (Export-Clixml). Nobody, including the operator running the script, sees it. Retrieve it later in
  your own console with:
      (Import-Clixml <file>) | ConvertFrom-SecureString -AsPlainText      # PowerShell 7
      or, in PowerShell 5.1:
      $s = Import-Clixml <file>; [Runtime.InteropServices.Marshal]::PtrToStringUni([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
  then move it to your password manager and delete the .dpapi file.

  Steps
    1. Check the old archive exists and there is enough free space (extraction ~5.4 GB + new archive ~3.2 GB).
    2. Extract to the temporary folder (old password).
    3. Verify the number of extracted files against the figure declared in PROVENANCE.md.
    4. Re-compress to _custodia_tfm_originales_v2.7z with AES-256 and encrypted headers (-mhe=on) (new password).
    5. Test the new archive (7z t) (new password) and require exit code 0.
    6. Write the SHA-256 of the new archive.
    7. Only then: delete the temporary folder, the old .7z and .sha256, the leaked password file, rename v2 -> final.
    8. Print a summary (files, bytes, SHA-256). Never a password.

  Nothing is deleted before step 7. On any failure the script stops and the old archive stays intact. Leftovers of a
  previous failed run (temporary folder, v2 archive) are removed at the start.

.NOTES
  Requires 7-Zip (7z.exe) in PATH or in C:\Program Files\7-Zip. PowerShell 5.1 compatible.
#>
[CmdletBinding()]
param(
    [string]$UserHome            = "C:\Users\dgp8",
    [string]$ArchiveName         = "_custodia_tfm_originales.7z",
    [string]$TempDir             = "C:\Users\dgp8\_tmp_rotacion",
    [string]$Provenance          = "",
    [long]  $RequiredFreeBytes   = 10GB,
    [string]$OldPasswordFile     = "",
    [string]$NewPasswordDpapiFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# $PSScriptRoot is not populated while parameter defaults are evaluated in PowerShell 5.1: resolve here
if ($Provenance -eq "") {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Provenance = Join-Path $ScriptDir "..\PROVENANCE.md"
}

function Fail([string]$msg) {
    Write-Host ""
    Write-Host "ABORTED: $msg" -ForegroundColor Red
    Write-Host "The old archive has NOT been modified." -ForegroundColor Yellow
    exit 1
}
function Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

$NonInteractive = ($OldPasswordFile -ne "" -and $NewPasswordDpapiFile -ne "")
if (($OldPasswordFile -ne "") -xor ($NewPasswordDpapiFile -ne "")) { Fail "Give both -OldPasswordFile and -NewPasswordDpapiFile, or neither." }

# ---------------------------------------------------------------- paths
$OldArchive   = Join-Path $UserHome $ArchiveName
$OldSha       = "$OldArchive.sha256"
$NewArchive   = Join-Path $UserHome ($ArchiveName -replace "\.7z$", "_v2.7z")
$NewSha       = "$NewArchive.sha256"
$PasswordFile = Join-Path $UserHome "_custodia_tfm_originales.password.txt"

# ---------------------------------------------------------------- 7-Zip
$SevenZip = $null
$cmd = Get-Command 7z -ErrorAction SilentlyContinue
if ($cmd) { $SevenZip = $cmd.Source }
if (-not $SevenZip) {
    foreach ($candidate in @("C:\Program Files\7-Zip\7z.exe", "C:\Program Files (x86)\7-Zip\7z.exe", "$env:LOCALAPPDATA\Programs\7-Zip\7z.exe")) {
        if (Test-Path $candidate) { $SevenZip = $candidate; break }
    }
}
if (-not $SevenZip) { Fail "7z.exe not found (PATH or C:\Program Files\7-Zip)." }
Write-Host "7-Zip: $SevenZip"
Write-Host ("Mode: {0}" -f $(if ($NonInteractive) { "non-interactive (old password from file, new password generated -> DPAPI)" } else { "interactive (7-Zip prompts)" }))

# ---------------------------------------------------------------- 1. preconditions
Step "1/8 Preconditions"
if (-not (Test-Path $OldArchive)) { Fail "Old archive not found: $OldArchive" }
$oldItem = Get-Item $OldArchive
Write-Host ("Old archive: {0} ({1:N0} bytes)" -f $OldArchive, $oldItem.Length)

$drive = Get-PSDrive -Name ($UserHome.Substring(0, 1))
if ($drive.Free -lt $RequiredFreeBytes) {
    Fail ("Not enough free space on {0}: {1:N1} GB free, {2:N1} GB required." -f $drive.Name, ($drive.Free / 1GB), ($RequiredFreeBytes / 1GB))
}
Write-Host ("Free space on {0}: {1:N1} GB" -f $drive.Name, ($drive.Free / 1GB))

# -LiteralPath: the project path contains "[Pro]", which Test-Path/Get-Content would treat as a wildcard
if (-not (Test-Path -LiteralPath $Provenance)) { Fail "PROVENANCE.md not found: $Provenance" }
$prov = Get-Content -LiteralPath $Provenance -Raw -Encoding UTF8
$m = [regex]::Match($prov, "Contenido del archivo:\s*([\d\.]+)\s*ficheros")
if (-not $m.Success) { Fail "Could not read the declared file count from PROVENANCE.md" }
[int]$DeclaredFiles = [int]($m.Groups[1].Value -replace "\.", "")
Write-Host "Declared file count in PROVENANCE.md: $DeclaredFiles"

# passwords (non-interactive mode): never displayed
$OldPw = ""
$NewPw = ""
if ($NonInteractive) {
    if (-not (Test-Path $OldPasswordFile)) { Fail "Old password file not found: $OldPasswordFile" }
    $OldPw = (Get-Content -Path $OldPasswordFile -Raw).Trim()
    if ($OldPw.Length -lt 8) { Fail "Old password file looks empty or too short." }
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $NewPw = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
    if ($NewPw.Length -ne 32) { Fail "Password generation failed." }
    # store it DPAPI-protected (bound to this Windows account) BEFORE using it, so it cannot be lost if a later step fails
    $secure = ConvertTo-SecureString -String $NewPw -AsPlainText -Force
    $secure | Export-Clixml -Path $NewPasswordDpapiFile
    if (-not (Test-Path $NewPasswordDpapiFile)) { Fail "Could not write the DPAPI-protected password file." }
    Write-Host "New password generated (32 chars) and stored DPAPI-protected in $NewPasswordDpapiFile (not displayed)."
}
$OldPwArg = $(if ($NonInteractive) { "-p$OldPw" } else { "-p" })
$NewPwArg = $(if ($NonInteractive) { "-p$NewPw" } else { "-p" })

# leftovers of a previous failed run (safe: the old archive is untouched)
if (Test-Path $TempDir)    { Write-Host "Removing leftover temporary folder $TempDir"; Remove-Item -Path $TempDir -Recurse -Force }
if (Test-Path $NewArchive) { Write-Host "Removing leftover $NewArchive"; Remove-Item -Path $NewArchive -Force }
if (Test-Path $NewSha)     { Remove-Item -Path $NewSha -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# ---------------------------------------------------------------- 2. extract (OLD password)
Step "2/8 Extracting the old archive"
& $SevenZip x $OldPwArg "-o$TempDir" -bd -bso0 $OldArchive
if ($LASTEXITCODE -ne 0) { Fail "7z x returned exit code $LASTEXITCODE (wrong password or damaged archive)." }

# ---------------------------------------------------------------- 3. verify extracted count
Step "3/8 Verifying the extracted file count"
$extracted = @(Get-ChildItem -Path $TempDir -Recurse -File)
$extractedBytes = ($extracted | Measure-Object -Property Length -Sum).Sum
Write-Host ("Extracted: {0} files, {1:N0} bytes" -f $extracted.Count, $extractedBytes)
if ($extracted.Count -ne $DeclaredFiles) { Fail "Extracted $($extracted.Count) files but PROVENANCE.md declares $DeclaredFiles." }
$roots = @(Get-ChildItem -Path $TempDir -Force)
if ($roots.Count -ne 1) { Fail "Expected exactly one top-level entry inside $TempDir, found $($roots.Count)." }
$RootName = $roots[0].Name

# ---------------------------------------------------------------- 4. compress (NEW password)
Step "4/8 Creating the new archive (AES-256, encrypted headers)"
Push-Location $TempDir
try {
    & $SevenZip a -t7z -mx=1 -mhe=on $NewPwArg -bd -bso0 $NewArchive $RootName
    $rc = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($rc -ne 0) { Fail "7z a returned exit code $rc." }
if (-not (Test-Path $NewArchive)) { Fail "New archive was not created." }

# ---------------------------------------------------------------- 5. test (NEW password)
Step "5/8 Testing the new archive"
& $SevenZip t $NewPwArg -bd -bso0 $NewArchive
if ($LASTEXITCODE -ne 0) { Fail "7z t returned exit code ${LASTEXITCODE}: the new archive did not verify." }
[int]$TestedFiles = $extracted.Count
Write-Host "New archive verified (7z t exit code 0)."

# passwords are no longer needed in memory
$OldPw = ""; $NewPw = ""; $OldPwArg = ""; $NewPwArg = ""
[System.GC]::Collect()

# ---------------------------------------------------------------- 6. hash
Step "6/8 Computing SHA-256 of the new archive"
$hash = (Get-FileHash -Path $NewArchive -Algorithm SHA256).Hash.ToLower()
$newItem = Get-Item $NewArchive
Write-Host ("New archive: {0:N0} bytes, SHA-256 {1}" -f $newItem.Length, $hash)

# ---------------------------------------------------------------- 7. cleanup and rename (only now)
Step "7/8 Everything verified. Removing the temporary folder, the old archive and the leaked password file."
Remove-Item -Path $TempDir -Recurse -Force
if (Test-Path $OldSha)       { Remove-Item -Path $OldSha -Force }
if (Test-Path $PasswordFile) { Remove-Item -Path $PasswordFile -Force; Write-Host "Removed $PasswordFile" }
if ($NonInteractive -and (Test-Path $OldPasswordFile) -and ($OldPasswordFile -ne $PasswordFile)) { Remove-Item -Path $OldPasswordFile -Force; Write-Host "Removed $OldPasswordFile" }
Remove-Item -Path $OldArchive -Force
Rename-Item -Path $NewArchive -NewName $ArchiveName
$FinalArchive = Join-Path $UserHome $ArchiveName
"$hash  $ArchiveName" | Out-File -FilePath "$FinalArchive.sha256" -Encoding ascii -NoNewline

# ---------------------------------------------------------------- 8. summary
Step "8/8 Summary"
$final = Get-Item $FinalArchive
Write-Host ("Archive : {0}" -f $FinalArchive)
Write-Host ("Files   : {0} (declared {1})" -f $TestedFiles, $DeclaredFiles)
Write-Host ("Bytes   : {0:N0}" -f $final.Length)
Write-Host ("SHA-256 : {0}" -f $hash)
Write-Host ("Hash file: {0}.sha256" -f $FinalArchive)
if ($NonInteractive) {
    Write-Host ("Password: DPAPI-protected in {0} - retrieve it in YOUR console, move it to the password manager, delete the file." -f $NewPasswordDpapiFile) -ForegroundColor Green
} else {
    Write-Host "Password rotated. Keep it in your password manager." -ForegroundColor Green
}
exit 0
