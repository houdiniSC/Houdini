<#
.SYNOPSIS
  Encrypt / decrypt a Hermes install config (.hcfg, HERMESCFG1 format).

.DESCRIPTION
  Pure PowerShell implementation - no WSL, Python or venv required.
  The output is byte-compatible with config-tool/encrypt-config.py and with
  the installer's decrypt_hcfg() (PBKDF2-HMAC-SHA256, 600k iterations,
  AES-128-CBC + HMAC-SHA256 Fernet token).

  Works on Windows PowerShell 5.1 (.NET Framework 4.7.2+) and PowerShell 7.
  The password can be supplied as -Password or via $env:ENCRYPT_CFG_PASSWORD
  (useful for scripts; note it then appears in the process command line).

.EXAMPLE
  .\encrypt-config.ps1 C:\path\install-config.json
  .\encrypt-config.ps1 C:\path\install-config.hcfg -Decrypt -OutputFile out.json
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$InputFile = "",

    [string]$OutputFile = "",

    [switch]$Decrypt,

    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$Magic = "HERMESCFG1"
$Iterations = 600000

function Get-PasswordInput {
    param([string]$Prompt)
    if (-not [string]::IsNullOrEmpty($env:ENCRYPT_CFG_PASSWORD)) {
        return $env:ENCRYPT_CFG_PASSWORD
    }
    $sec = Read-Host -AsSecureString -Prompt $Prompt
    if ($null -eq $sec) {
        return ""
    }
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Get-DerivedKey {
    param([string]$Pass, [byte[]]$Salt)
    $pbkdf2 = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
        $Pass, $Salt, $Iterations,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    try {
        return $pbkdf2.GetBytes(32)
    }
    finally {
        $pbkdf2.Dispose()
    }
}

function Get-UnixTimeBytes {
    $ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $bytes = [BitConverter]::GetBytes([uint64]$ts)
    [Array]::Reverse($bytes)
    return ,$bytes
}

function Invoke-AesCbcEncrypt {
    param([byte[]]$Plain, [byte[]]$AesKey, [byte[]]$Iv)
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.KeySize = 128
    $aes.BlockSize = 128
    $aes.Key = $AesKey
    $aes.IV = $Iv
    $enc = $aes.CreateEncryptor()
    $ms = [System.IO.MemoryStream]::new()
    $cs = [System.Security.Cryptography.CryptoStream]::new(
        $ms, $enc, [System.Security.Cryptography.CryptoStreamMode]::Write)
    try {
        $cs.Write($Plain, 0, $Plain.Length)
        $cs.FlushFinalBlock()
        return ,$ms.ToArray()
    }
    finally {
        $cs.Dispose()
        $ms.Dispose()
        $enc.Dispose()
        $aes.Dispose()
    }
}

function Invoke-AesCbcDecrypt {
    param([byte[]]$Cipher, [byte[]]$AesKey, [byte[]]$Iv)
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.KeySize = 128
    $aes.BlockSize = 128
    $aes.Key = $AesKey
    $aes.IV = $Iv
    $dec = $aes.CreateDecryptor()
    $ms = [System.IO.MemoryStream]::new($Cipher)
    $cs = [System.Security.Cryptography.CryptoStream]::new(
        $ms, $dec, [System.Security.Cryptography.CryptoStreamMode]::Read)
    $out = [System.IO.MemoryStream]::new()
    try {
        $cs.CopyTo($out)
        return ,$out.ToArray()
    }
    finally {
        $out.Dispose()
        $cs.Dispose()
        $ms.Dispose()
        $dec.Dispose()
        $aes.Dispose()
    }
}

function Get-RandomBytes {
    param([int]$Count)
    $buf = New-Object byte[] $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buf)
        return ,$buf
    }
    finally {
        $rng.Dispose()
    }
}

function New-HermesConfig {
    param([string]$Src, [string]$Out, [string]$Pass)
    if ([string]::IsNullOrEmpty($Pass)) {
        throw "Empty password is not allowed."
    }
    $text = [System.IO.File]::ReadAllText($Src, [System.Text.Encoding]::UTF8)
    try {
        $null = $text | ConvertFrom-Json
    }
    catch {
        throw "Invalid JSON in $Src : $($_.Exception.Message)"
    }
    $plain = [System.IO.File]::ReadAllBytes($Src)

    $salt = Get-RandomBytes 16
    $key = Get-DerivedKey -Pass $Pass -Salt $salt
    $iv = Get-RandomBytes 16
    # NOTE: match the Fernet layout used by this environment's cryptography
    # library: signing key = first 16 bytes, AES key = last 16 bytes.
    $encKey = [byte[]]($key[16..31])
    $macKey = [byte[]]($key[0..15])
    $cipher = Invoke-AesCbcEncrypt -Plain $plain -AesKey $encKey -Iv $iv
    $tsBytes = Get-UnixTimeBytes

    $payload = New-Object byte[] (1 + 8 + 16 + $cipher.Length)
    $payload[0] = 0x80
    [Array]::Copy($tsBytes, 0, $payload, 1, 8)
    [Array]::Copy($iv, 0, $payload, 9, 16)
    [Array]::Copy($cipher, 0, $payload, 25, $cipher.Length)

    $hmac = [System.Security.Cryptography.HMACSHA256]::new($macKey)
    try {
        $sig = $hmac.ComputeHash($payload)
    }
    finally {
        $hmac.Dispose()
    }
    $token = New-Object byte[] ($payload.Length + 32)
    [Array]::Copy($payload, 0, $token, 0, $payload.Length)
    [Array]::Copy($sig, 0, $token, $payload.Length, 32)

    $tokenB64 = [Convert]::ToBase64String($token).Replace('+', '-').Replace('/', '_')
    $content = $Magic + "`n" + [Convert]::ToBase64String($salt) + "`n" + $tokenB64 + "`n"
    [System.IO.File]::WriteAllText(
        $Out, $content, (New-Object System.Text.UTF8Encoding($false)))
    return "encrypted: $Out"
}

function Read-HermesConfig {
    param([string]$Src, [string]$Out, [string]$Pass)
    if ([string]::IsNullOrEmpty($Pass)) {
        throw "Empty password is not allowed."
    }
    $lines = [System.IO.File]::ReadAllLines($Src)
    if ($lines.Count -lt 3 -or $lines[0] -ne $Magic) {
        throw "Not a Hermes encrypted config (.hcfg) file."
    }
    try {
        $salt = [Convert]::FromBase64String($lines[1])
        $token = [Convert]::FromBase64String(
            $lines[2].Replace('-', '+').Replace('_', '/'))
    }
    catch {
        throw "Corrupted .hcfg file (bad base64): $($_.Exception.Message)"
    }
    if ($token.Length -lt 57) {
        throw "Corrupted .hcfg file (token too short)."
    }

    $key = Get-DerivedKey -Pass $Pass -Salt $salt
    $payload = New-Object byte[] ($token.Length - 32)
    [Array]::Copy($token, 0, $payload, 0, $payload.Length)
    $sig = New-Object byte[] 32
    [Array]::Copy($token, $token.Length - 32, $sig, 0, 32)

    $macKey = [byte[]]($key[0..15])
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($macKey)
    try {
        $calc = $hmac.ComputeHash($payload)
    }
    finally {
        $hmac.Dispose()
    }
    $match = $true
    for ($i = 0; $i -lt 32; $i++) {
        if ($calc[$i] -ne $sig[$i]) {
            $match = $false
            break
        }
    }
    if (-not $match) {
        throw "Wrong password or corrupted .hcfg file."
    }

    $iv = New-Object byte[] 16
    [Array]::Copy($payload, 9, $iv, 0, 16)
    $cipher = New-Object byte[] ($payload.Length - 25)
    [Array]::Copy($payload, 25, $cipher, 0, $cipher.Length)
    $encKey = [byte[]]($key[16..31])
    $plain = Invoke-AesCbcDecrypt -Cipher $cipher -AesKey $encKey -Iv $iv

    try {
        $null = [System.Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
    }
    catch {
        throw "Decrypted config is not valid JSON: $($_.Exception.Message)"
    }
    [System.IO.File]::WriteAllBytes($Out, $plain)
    return "decrypted: $Out"
}

# ---------------------------------------------------------------------------
if ([string]::IsNullOrEmpty($InputFile)) {
    Write-Host ""
    Write-Host "  Hermes config encryption tool (.hcfg / HERMESCFG1)"
    Write-Host ""
    Write-Host "  Encrypt:  .\encrypt-config.ps1 C:\path\install-config.json"
    Write-Host "  Decrypt:  .\encrypt-config.ps1 C:\path\install-config.hcfg -Decrypt"
    Write-Host ""
    Write-Host "  Optional: -OutputFile <path>  -Password <pw>  (or set ENCRYPT_CFG_PASSWORD)"
    Write-Host ""
    exit 1
}

if (-not (Test-Path -LiteralPath $InputFile)) {
    Write-Host "[encrypt-config] File not found: $InputFile"
    exit 1
}
$Src = (Resolve-Path -LiteralPath $InputFile).Path

if ([string]::IsNullOrEmpty($OutputFile)) {
    if ($Decrypt) {
        $OutputFile = [System.IO.Path]::ChangeExtension($Src, ".json")
    }
    else {
        $OutputFile = [System.IO.Path]::ChangeExtension($Src, ".hcfg")
    }
}

try {
    if ($Decrypt) {
        if ([string]::IsNullOrEmpty($Password)) {
            $Password = Get-PasswordInput -Prompt "Decryption password"
        }
        $msg = Read-HermesConfig -Src $Src -Out $OutputFile -Pass $Password
    }
    else {
        if ([string]::IsNullOrEmpty($Password)) {
            $Password = Get-PasswordInput -Prompt "Encryption password"
            $Confirm = Get-PasswordInput -Prompt "Confirm password"
            if ($Password -ne $Confirm) {
                Write-Host "[encrypt-config] Passwords do not match."
                exit 1
            }
        }
        $msg = New-HermesConfig -Src $Src -Out $OutputFile -Pass $Password
    }
    Write-Host "[encrypt-config] $msg"
    Write-Host "[encrypt-config] Upload this file from the installer's first page with its password."
}
catch {
    Write-Host "[encrypt-config] FAILED: $($_.Exception.Message)"
    exit 1
}
