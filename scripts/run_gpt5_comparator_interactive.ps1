$ErrorActionPreference = "Stop"
$secureKey = Read-Host "Enter CHATANYWHERE_API_KEY for this one process" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:CHATANYWHERE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    python scripts/run_e4_gpt5_comparator.py
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:CHATANYWHERE_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
Write-Host "Comparator finished with exit code $exitCode. You may close this window."
Read-Host "Press Enter"
exit $exitCode
