<#
install-wsl.ps1 -- create an isolated WSL distro (HoudiniGateway) and
run the Houdini terminal installer (TUI) inside it.

Isolation model: the gateway runs inside its OWN WSL distribution
(separate filesystem, home, processes, and services) -- like OpenClawGateway.

WORKS BOTH WAYS:

  1) One-liner via irm | iex (local path or URL) -- recommended
     Note: irm needs an ABSOLUTE path or file:// URI (relative paths are rejected).
     $src = 'C:\path\to\Houdini'               # local package root
     irm "$src\install-wsl.ps1" | iex

     # or from inside the package root (no $src needed):
     cd C:\path\to\Houdini
     irm "$pwd\install-wsl.ps1" | iex

     $src = 'https://host/path'                # hosted package
     irm "$src/install-wsl.ps1" | iex

     # optional overrides (caller variables, before the pipe):
     $Distro = 'HoudiniGateway'; irm "$pwd\install-wsl.ps1" | iex

  2) Classic script run
     .\install-wsl.ps1 -Distro HoudiniGateway -RootfsPath C:\tmp\ubuntu.tar.gz

Configuration precedence: CLI args (script run) > caller variables > env > defaults.
Caller variables: $src, $Distro, $RootfsPath
Env vars:         HERMES_SRC, HOUDINI_DISTRO (HERMES_DISTRO fallback), HERMES_ROOTFS

For URL sources the script fetches the full repo zip (codeload) into a temp
dir; the package root is the extracted repo root (src/, knowledge-pack/,
rootfs/). Rootfs source (default): bundled rootfs chunks when present,
otherwise Ubuntu 24.04 WSL rootfs from cdimages.ubuntu.com (WSL images moved
there from cloud-images.ubuntu.com; the old path 404s).
#>

$ErrorActionPreference = "Stop"

# ---- CLI args for classic script runs (no param() -> irm | iex safe) ----
for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "-Source"     { $Source = $args[++$i] }
        "-Distro"     { $Distro = $args[++$i] }
        "-RootfsPath" { $RootfsPath = $args[++$i] }
        default       { Write-Host "[bootstrap] WARNING: unknown argument '$($args[$i])'" -ForegroundColor Yellow }
    }
}

& {
    function Log($msg) {
        Write-Host "[bootstrap] $msg" -ForegroundColor Cyan
    }

    function Fail($msg) {
        Write-Host "[bootstrap] ERROR: $msg" -ForegroundColor Red
        exit 1
    }

    # ---- 0) Resolve package location (dir or URL) ------------------------
    # The package root contains src/installer-tui.py + knowledge-pack/ (and
    # rootfs/ for the bundled distro image). All code lives under src/.
    function Test-PackageRoot {
        param([string]$Candidate)
        return (
            (Test-Path (Join-Path $Candidate "src\installer-tui.py")) -and
            (Test-Path (Join-Path $Candidate "knowledge-pack"))
        )
    }

    function Find-PackageDir {
        param([string]$Start)
        $dir = if ($Start) { $Start } else { (Get-Location).Path }
        for ($level = 0; $level -lt 6; $level++) {
            $candidates = @($dir)
            $candidates += @(Get-ChildItem -Directory -LiteralPath $dir -ErrorAction SilentlyContinue |
                Sort-Object Name | ForEach-Object { $_.FullName })
            foreach ($candidate in $candidates) {
                if (Test-PackageRoot $candidate) {
                    return $candidate
                }
            }
            $parent = Split-Path -Parent $dir
            if (-not $parent -or $parent -eq $dir) { break }
            $dir = $parent
        }
        return $null
    }

    $Here = $Source
    if (-not $Here) { $Here = $PSScriptRoot }
    if (-not $Here -and $MyInvocation.MyCommand.Path) {
        $Here = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if (-not $Here) { $Here = $src }
    if (-not $Here) { $Here = $env:HERMES_SRC }
    if (-not $Here) { $Here = Find-PackageDir }
    # If the caller pointed at the src/ folder itself, normalize to the root.
    if ($Here -and -not ($Here -match '^https?://') -and
        (Test-Path (Join-Path $Here "installer-tui.py")) -and
        (Test-Path (Join-Path $Here "..\knowledge-pack"))) {
        $Here = Split-Path -Parent $Here
    }
    if (-not $Here) {
        Fail "Could not locate the package. Set `$src before piping, e.g.:
`$src = 'C:\path\to\Houdini'
irm `"`$src\install-wsl.ps1`" | iex"
    }

    $Remote = $Here -match '^https?://'
    $InstallerDir = $Here

    if ($Remote) {
        $base = $Here.TrimEnd('/')
        $InstallerDir = Join-Path $env:TEMP ("houdini-package-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $InstallerDir | Out-Null
        Log "Fetching package from $base -> $InstallerDir"

        $fetched = $false
        # GitHub raw base -> full repo zip (ships src/, knowledge-pack/, rootfs/)
        $ghMatch = [regex]::Match($base, '^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/')
        if ($ghMatch.Success) {
            $repoZip = Join-Path $InstallerDir "repo.zip"
            try {
                $repoUrl = "https://codeload.github.com/$($ghMatch.Groups[1].Value)/$($ghMatch.Groups[2].Value)/zip/refs/heads/main"
                Log "Downloading full repo zip: $repoUrl"
                Invoke-WebRequest -UseBasicParsing -Uri $repoUrl -OutFile $repoZip -TimeoutSec 300
                $exDir = Join-Path $InstallerDir "repo-extract"
                Expand-Archive -Path $repoZip -DestinationPath $exDir -Force
                $sub = Get-ChildItem $exDir -Directory | Where-Object { $_.Name -ne "__MACOSX" } | Select-Object -First 1
                if ($sub -and (Test-PackageRoot $sub.FullName)) {
                    $InstallerDir = $sub.FullName
                    $fetched = $true
                }
            } catch {
                Log "WARNING: repo zip fetch failed: $($_.Exception.Message)"
            }
        }

        if (-not $fetched) {
            # Flat fallback for non-GitHub hosts: src/ files + knowledge-pack.zip
            $srcDir = Join-Path $InstallerDir "src"
            New-Item -ItemType Directory -Path $srcDir | Out-Null
            foreach ($f in @("install-wsl.ps1", "install-ubuntu.sh", "installer-tui.py",
                             "installer_core.py", "keys-manager.py", "secrets.env.example")) {
                try {
                    Invoke-WebRequest -UseBasicParsing -Uri "$base/src/$f" -OutFile (Join-Path $srcDir $f) -TimeoutSec 60
                } catch { }
            }
            $kpZip = Join-Path $InstallerDir "knowledge-pack.zip"
            try { Invoke-WebRequest -UseBasicParsing -Uri "$base/knowledge-pack.zip" -OutFile $kpZip -TimeoutSec 60 } catch { }
            if ((Test-Path $kpZip) -and (Get-Item $kpZip).Length -gt 0) {
                Expand-Archive -Path $kpZip -DestinationPath (Join-Path $InstallerDir "knowledge-pack") -Force
                Remove-Item -LiteralPath $kpZip -Force
            }
            $fetched = Test-PackageRoot $InstallerDir
        }
        if (-not $fetched) {
            Fail "Could not fetch the installer package from $base (installer-tui.py missing)."
        }
        Log "Package staged at $InstallerDir (kept for the installer session)."
    }

    # ---- 1) Options: caller vars > env > defaults -------------------------
    if (-not $Distro)     { $Distro = $env:HOUDINI_DISTRO }
    if (-not $Distro)     { $Distro = $env:HERMES_DISTRO }
    if (-not $Distro)     { $Distro = "HoudiniGateway" }
    if (-not $RootfsPath) { $RootfsPath = $env:HERMES_ROOTFS }

    # ---- 2) Prerequisites ------------------------------------------------
    if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
        Fail "wsl is not available. Enable WSL first (wsl --install)."
    }

    $existing = wsl --list --quiet 2>$null | Where-Object { $_ -match [regex]::Escape($Distro) }
    # wsl --list output can be UTF-16 with null bytes on some Windows builds;
    # strip NUL bytes and fall back to wsl -l -v parsing if the list is empty.
    if (-not $existing) {
        $quietRaw = (& wsl.exe --list --quiet 2>$null | Out-String) -replace "`0", ""
        if ($quietRaw -match [regex]::Escape($Distro)) {
            $existing = $Distro
        }
    }
    if (-not $existing) {
        $verboseList = (& wsl.exe --list --verbose 2>$null | Out-String) -replace "`0", ""
        if ($verboseList -match [regex]::Escape($Distro)) {
            $existing = $Distro
        }
    }
    if ($existing) {
        Log "Distro '$Distro' already exists -- reusing it."
    } else {
        # -- Rootfs --------------------------------------------------------
        $rootfs = $RootfsPath
        if (-not $rootfs) {
            $tmp = Join-Path $env:TEMP "hermes-rootfs.tar.gz"
            if (-not (Test-Path $tmp)) {
                # Local git clone (or extracted repo zip): the rootfs chunks
                # are already on disk - reassemble them instead of downloading.
                $localParts = @()
                foreach ($c in @("hermes-rootfs.tar.gz.00", "hermes-rootfs.tar.gz.01",
                                 "hermes-rootfs.tar.gz.02", "hermes-rootfs.tar.gz.03")) {
                    $p = Join-Path $InstallerDir "rootfs\$c"
                    if (Test-Path $p) { $localParts += $p }
                }
                if ($localParts.Count -eq 4) {
                    try {
                        Log "Reassembling rootfs from local chunks (no download)..."
                        $fs = [System.IO.File]::OpenWrite($tmp)
                        foreach ($p in $localParts) {
                            $b = [System.IO.File]::ReadAllBytes($p)
                            $fs.Write($b, 0, $b.Length)
                        }
                        $fs.Close()
                        $sumsFile = Join-Path $InstallerDir "rootfs\SHA256SUMS"
                        if (Test-Path $sumsFile) {
                            $expected = ((Get-Content $sumsFile |
                                Where-Object { $_ -match 'hermes-rootfs\.tar\.gz$' } |
                                Select-Object -First 1).Trim().Split(" ")[0])
                            if ($expected) {
                                $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLowerInvariant()
                                if ($actual -ne $expected) {
                                    throw "local rootfs SHA256 mismatch (expected $expected, got $actual)"
                                }
                                Log "Rootfs SHA256 verified from local chunks ($actual)."
                            }
                        }
                    } catch {
                        Log "WARNING: local rootfs reassembly failed: $($_.Exception.Message)"
                        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                    }
                }
                # GitHub-hosted rootfs chunks (raw base) — no Ubuntu download needed
                $ghr = [regex]::Match($base, '^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/')
                if ($ghr.Success) {
                    try {
                        Log "Downloading rootfs chunks from GitHub..."
                        $parts = @()
                        foreach ($c in @("hermes-rootfs.tar.gz.00", "hermes-rootfs.tar.gz.01",
                                         "hermes-rootfs.tar.gz.02", "hermes-rootfs.tar.gz.03")) {
                            $p = Join-Path $env:TEMP $c
                            Invoke-WebRequest -UseBasicParsing -Uri "$base/rootfs/$c" -OutFile $p -TimeoutSec 900
                            $parts += $p
                        }
                        $fs = [System.IO.File]::OpenWrite($tmp)
                        foreach ($p in $parts) {
                            $b = [System.IO.File]::ReadAllBytes($p)
                            $fs.Write($b, 0, $b.Length)
                        }
                        $fs.Close()
                        $rootfs_mb = [math]::Round((Get-Item $tmp).Length / 1MB)
                        Log "Rootfs reassembled from GitHub chunks ($rootfs_mb MB)"
                        try {
                            $sumsRaw = (Invoke-WebRequest -UseBasicParsing -Uri "$base/rootfs/SHA256SUMS" -TimeoutSec 60).Content
                            $sums = if ($sumsRaw -is [byte[]]) { [System.Text.Encoding]::UTF8.GetString($sumsRaw) } else { [string]$sumsRaw }
                            $expected = ($sums -split '\r?\n' | Where-Object { $_ -match 'hermes-rootfs\.tar\.gz$' } | Select-Object -First 1).Trim().Split(" ")[0]
                            if ($expected) {
                                $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLowerInvariant()
                                if ($actual -ne $expected) {
                                    Remove-Item -LiteralPath $tmp -Force
                                    throw "rootfs SHA256 mismatch (expected $expected, got $actual)"
                                }
                                Log "Rootfs SHA256 verified from GitHub ($actual)."
                            }
                        } catch {
                            Log "WARNING: could not verify rootfs checksum: $($_.Exception.Message)"
                        }
                    } catch {
                        Log "WARNING: GitHub rootfs download failed: $($_.Exception.Message) - falling back to Ubuntu."
                        Remove-Item -LiteralPath $tmp -Force
                    }
                }
                if (-not (Test-Path $tmp)) {
                    Log "Downloading Ubuntu 24.04 rootfs..."
                    $arch = if ($env:PROCESSOR_ARCHITECTURE -match "ARM") { "arm64" } else { "amd64" }
                    $rootfsUrl = "https://cdimages.ubuntu.com/ubuntu-wsl/noble/daily-live/current/noble-wsl-$arch.wsl"
                    Log "Downloading $rootfsUrl"
                    Invoke-WebRequest -UseBasicParsing -Uri $rootfsUrl -OutFile $tmp -TimeoutSec 600

                    # -- verify SHA256 against the published checksum file ------
                    try {
                        $sumsRaw = (Invoke-WebRequest -UseBasicParsing -Uri "https://cdimages.ubuntu.com/ubuntu-wsl/noble/daily-live/current/SHA256SUMS" -TimeoutSec 60).Content
                        $sums = if ($sumsRaw -is [byte[]]) { [System.Text.Encoding]::UTF8.GetString($sumsRaw) } else { [string]$sumsRaw }
                        $expected = ($sums -split '\r?\n' | Where-Object { $_ -match "\*noble-wsl-$arch\.wsl" } | Select-Object -First 1).Trim().Split(" ")[0]
                        if ($expected) {
                            $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLowerInvariant()
                            if ($actual -ne $expected) {
                                Remove-Item -LiteralPath $tmp -Force
                                Fail "Rootfs checksum mismatch. Expected $expected, got $actual. Delete $tmp and re-run."
                            }
                            Log "Rootfs SHA256 verified ($actual)."
                        }
                    } catch {
                        Log "WARNING: could not verify rootfs checksum: $($_.Exception.Message)"
                    }
                }
            }
            $rootfs = $tmp
        }
        if (-not (Test-Path $rootfs)) {
            Fail "Rootfs not found: $rootfs"
        }

        # -- Import isolated distro ----------------------------------------
        $installDir = Join-Path $env:LOCALAPPDATA "WSL\$Distro"
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        Log "Importing '$Distro' from $rootfs"
        wsl --import $Distro $installDir $rootfs
        if ($LASTEXITCODE -ne 0) {
            # Safety net: the distro check above can miss a registered distro
            # (UTF-16 output, name casing). If import says it already exists,
            # treat this as an update run instead of failing.
            $errText = (& wsl.exe --list --verbose 2>&1 | Out-String) -replace "`0", ""
            if ($errText -match [regex]::Escape($Distro)) {
                Log "Import reported the distro already exists -- switching to UPDATE mode."
                $existing = $Distro
            } else {
                Fail "wsl --import failed. Check the error above and that '$rootfs' is a valid rootfs."
            }
        }
    }

    # ---- 2b) Update mode (distro exists, rootfs cached) ------------------
    # Default when the distro is already present: never re-import. Instead,
    # copy the fresh package (src/, knowledge-pack/) into the distro and run
    # the updated TUI from there -- no unregister, no reinstall, no download.
    # NOTE: knowledge-pack has thousands of small files; copying them one by
    # one through the 9p/DrvFs mount is extremely slow. A tar pipe (Windows
    # side tar -> wsl tar) streams them at native speed.
    $rootfsCached = (Test-Path (Join-Path $env:TEMP "hermes-rootfs.tar.gz")) -or
                    ($RootfsPath -and (Test-Path $RootfsPath))
    $Update = $true
    if ($existing) {
        if ($rootfsCached) {
            Log "Distro '$Distro' exists with cached rootfs -- UPDATE mode (copy package, keep everything)."
        } else {
            Log "Distro '$Distro' exists -- UPDATE mode (rootfs not cached; package updated in place)."
        }
        $guestDir = "/home/hermes/houdini"
        $wslDrive = $InstallerDir.Substring(0, 1).ToLowerInvariant()
        $wslRest = $InstallerDir.Substring(2).Replace("\", "/")
        $wslPkg = "/mnt/$wslDrive$wslRest"
        Log "Syncing package into '$Distro' ($guestDir) -- this may take a minute for the knowledge pack..."
        # tar bundle: Windows tar (bsdtar) archives src + knowledge-pack into
        # ONE file, which is copied across 9p as a single large stream, then
        # unpacked natively on the ext4 filesystem. Copying thousands of small
        # files one by one through the DrvFs mount would take many minutes.
        $tarName = "houdini-pkg.tar"
        $tarOut = Join-Path $env:TEMP $tarName
        $wslTar = "/mnt/" + $tarOut.Substring(0, 1).ToLowerInvariant() +
                  $tarOut.Substring(2).Replace("\", "/")
        if (Test-Path $tarOut) { Remove-Item -LiteralPath $tarOut -Force }
        try {
            # Git for Windows puts its own tar on PATH; the Windows (bsdtar)
            # binary must be called by absolute path so paths like C:\ work.
            $tarBin = "C:\Windows\System32\tar.exe"
            if (-not (Test-Path $tarBin)) { $tarBin = "tar.exe" }
            & $tarBin -C $InstallerDir -cf $tarOut src knowledge-pack install-ubuntu.sh 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $tarOut)) {
                Log "Bundle ready ($([math]::Round((Get-Item $tarOut).Length / 1MB, 1)) MB) -- unpacking inside distro..."
                # No stdin redirect: PowerShell can't do `< file`. The tar sits
                # in %TEMP% and is read from the distro via /mnt/c/... as a
                # single file, then extracted locally on ext4.
                wsl -d $Distro -u root -- bash -lc "mkdir -p '$guestDir' && tar -C '$guestDir' -xf '$wslTar'"
                if ($LASTEXITCODE -ne 0) {
                    Log "WARNING: tar unpack reported an error -- continuing with the mounted path."
                }
            } else {
                Log "WARNING: tar bundle failed -- falling back to mounted path."
            }
        } catch {
            Log "WARNING: package sync failed ($($_.Exception.Message)) -- continuing with the mounted path."
        }
        Remove-Item -LiteralPath $tarOut -Force -ErrorAction SilentlyContinue
        # ensure the guest copy has the latest files regardless of method
        wsl -d $Distro -u root -- bash -lc "chown -R hermes:hermes '$guestDir' 2>/dev/null; chmod +x '$guestDir/install-ubuntu.sh' 2>/dev/null || true"
    }

    # ---- 3) Inside setup: systemd + agent user + deps --------------------
    Log "Configuring systemd and the agent user inside '$Distro'..."
    $setup = @'
set -e
printf '[boot]\nsystemd=true\n' > /etc/wsl.conf
# dedicated agent user with passwordless sudo for the installer session
id hermes >/dev/null 2>&1 || useradd -m -s /bin/bash hermes
printf 'hermes ALL=(ALL) NOPASSWD: SETENV: ALL\n' > /etc/sudoers.d/hermes-bootstrap
chmod 440 /etc/sudoers.d/hermes-bootstrap
# fast path on re-runs: skip apt when the installer venv already exists
if [ -x /home/hermes/hermes-venv/bin/python ]; then
    :
else
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv curl git unzip
fi
# isolated venv for the installer: system pip conflicts with Debian packages
if [ ! -x /home/hermes/hermes-venv/bin/python ]; then
    python3 -m venv /home/hermes/hermes-venv
fi
/home/hermes/hermes-venv/bin/pip install -q textual cryptography 2>/dev/null || true
loginctl enable-linger hermes 2>/dev/null || true
'@
    # wsl.exe mangles multi-line / quoted arguments passed to `bash -c`
    # (newlines and quotes get split), so run the setup from a file on the
    # Windows side, visible inside the distro via /mnt/<drive>.
    $setupFile = Join-Path $InstallerDir "inside-setup.sh"
    $setupLf = $setup -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText(
        $setupFile, $setupLf, (New-Object System.Text.UTF8Encoding($false)))
    $setupDrive = $setupFile.Substring(0, 1).ToLowerInvariant()
    $setupRest = $setupFile.Substring(2).Replace("\", "/")
    $wslSetup = "/mnt/$setupDrive$setupRest"
    wsl -d $Distro -u root -- bash $wslSetup
    $setupExit = $LASTEXITCODE
    if ($setupExit -ne 0) {
        Fail "Inside-distro setup failed (script kept at $setupFile)."
    }
    Remove-Item -LiteralPath $setupFile -Force

    # restart distro so systemd + default user take effect
    wsl --terminate $Distro 2>$null
    Log "Restarted '$Distro' with systemd enabled."

    # ---- 4) Launch the terminal installer (TUI) inside the distro --------
    $drive = $InstallerDir.Substring(0, 1).ToLowerInvariant()
    $rest = $InstallerDir.Substring(2).Replace("\", "/")
    $installerPath = "/mnt/$drive$rest/src"
    $py = "/home/hermes/hermes-venv/bin/python"

    # Update mode: prefer the synced copy inside the distro (fresh code,
    # no dependence on the mounted Windows path staying put).
    if ($existing) {
        $guestSrc = "/home/hermes/houdini/src"
        if (wsl -d $Distro -u hermes -- bash -lc "test -f '$guestSrc/installer-tui.py'") {
            $installerPath = $guestSrc
            Log "Using updated package inside the distro ($guestSrc)."
        } else {
            Log "No synced copy found -- falling back to the mounted path."
        }
    }

    Log "Starting the Houdini terminal installer inside '$Distro'..."
    Log "Run the wizard directly in this terminal (Textual TUI)."
    wsl -d $Distro -u hermes -- bash -lc "$py '$installerPath/installer-tui.py'"
}
