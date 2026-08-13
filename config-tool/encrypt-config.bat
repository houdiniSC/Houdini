@echo off
setlocal EnableExtensions
rem ============================================================
rem  encrypt-config.bat - drag & drop install-config.json
rem  -> password-protected install-config.hcfg (HERMESCFG1)
rem
rem  Runs through WSL (HermesGateway preferred, Ubuntu fallback)
rem  with a small venv holding the cryptography package. The
rem  venv is created automatically on first use.
rem
rem  Optional: set ENCRYPT_CFG_PASSWORD first to skip the
rem  interactive prompts (convenient for scripts; the password
rem  will appear in the process command line).
rem ============================================================

set "SRC=%~1"
if "%SRC%"=="" goto :usage
if not exist "%SRC%" (
  echo [encrypt-config] File not found: "%SRC%"
  goto :end
)

set "DISTRO="
wsl -d HermesGateway true >nul 2>&1 && set "DISTRO=HermesGateway"
if not defined DISTRO wsl -d Ubuntu true >nul 2>&1 && set "DISTRO=Ubuntu"
if not defined DISTRO (
  echo [encrypt-config] No WSL distro found ^(HermesGateway or Ubuntu^).
  goto :end
)
echo [encrypt-config] Using WSL distro: %DISTRO%

rem -- ensure venv with cryptography (one-time, recreated if wiped) --
echo [encrypt-config] Checking WSL encryption environment...
wsl -d %DISTRO% -- bash -lc "test -x /tmp/hermes-cfg-venv/bin/python || (python3 -m venv /tmp/hermes-cfg-venv && /tmp/hermes-cfg-venv/bin/pip install -q cryptography)"
if not "%ERRORLEVEL%"=="0" (
  echo [encrypt-config] Failed to prepare the encryption environment.
  goto :end
)

rem -- convert Windows paths to WSL paths --
for /f "delims=" %%i in ('wsl -d %DISTRO% wslpath -u "%SRC%"') do set "IN=%%i"
for /f "delims=" %%i in ('wsl -d %DISTRO% wslpath -u "%~dp0encrypt-config.py"') do set "TOOL=%%i"
if not defined IN (
  echo [encrypt-config] Could not convert the file path to WSL.
  goto :end
)
for %%f in ("%SRC%") do set "OUTWIN=%%~dpnf.hcfg"
for /f "delims=" %%i in ('wsl -d %DISTRO% wslpath -u "%OUTWIN%"') do set "OUT=%%i"

rem -- optional password from env (skips the interactive prompt) --
set "PWARG="
if defined ENCRYPT_CFG_PASSWORD set "PWARG=--password %ENCRYPT_CFG_PASSWORD%"

echo [encrypt-config] Encrypting: "%SRC%"
wsl -d %DISTRO% -- bash -lc "exec /tmp/hermes-cfg-venv/bin/python '%TOOL%' '%IN%' -o '%OUT%' %PWARG%"
if not "%ERRORLEVEL%"=="0" (
  echo [encrypt-config] Encryption failed.
  goto :end
)

echo [encrypt-config] Done: "%OUTWIN%"
goto :end

:usage
echo.
echo  Drag and drop your install-config.json onto encrypt-config.bat
echo  to create a password-protected .hcfg file next to it.
echo.
echo  Usage:  encrypt-config.bat "C:\path\to\install-config.json"
echo.

:end
pause
endlocal
