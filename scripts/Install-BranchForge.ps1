# Windows PowerShell 5.1 compatible. Run as the normal Windows user, not administrator.
[CmdletBinding()]
param(
    [string]$Ref = 'master',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'BranchForge'),
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Download-File([string]$Url, [string]$Destination) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 900
            return
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host "Download interrupted; retrying ($attempt/3)..."
        }
    }
}

function Run-Installer([string]$Exe, [string]$Arguments) {
    $process = Start-Process -FilePath $Exe -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -eq 3010) { throw 'Windows requests a restart. Restart, then rerun setup.' }
    if ($process.ExitCode -ne 0) { throw "Installer failed with exit code $($process.ExitCode): $Exe" }
}

function Get-GitBlobHash([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $prefix = [Text.Encoding]::UTF8.GetBytes("blob $($bytes.Length)`0")
    $sha = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([byte[]]($prefix + $bytes)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Install-BranchForge {
    $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($arch -ne 'AMD64') { throw 'This installer requires an Intel/AMD 64-bit Windows laptop. ARM and 32-bit Windows need a separate setup.' }
    $os = Get-CimInstance Win32_OperatingSystem
    if ([version]$os.Version -lt [version]'10.0') { throw 'Windows 10/11 is required; Windows 11 is recommended.' }
    if ([double]$os.TotalVisibleMemorySize / 1MB -lt 8) {
        Write-Warning 'Less than 8 GB RAM: the UI may work, but real scans/detection may run out of memory.'
    }
    $root = [IO.Path]::GetFullPath($InstallRoot)
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($root).Substring(0, 1))
    if ($drive.Free -lt 8GB) { throw 'Please free at least 8 GB on the installation drive (scans require additional space).' }
    $cache = Join-Path $root 'downloads'
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    Write-Host "Installing in $root. No Git, administrator shell, or GPU toolkit required."

    Write-Host '[1/5] Downloading BranchForge code (not the large scan dataset)...'
    $headers = @{ 'User-Agent' = 'BranchForge-Windows-Setup'; Accept = 'application/vnd.github+json' }
    $api = 'https://api.github.com/repos/Toastyybread1/toralis-challenge'
    $commit = Invoke-RestMethod -Uri "$api/commits/$([Uri]::EscapeDataString($Ref))" -Headers $headers
    $revision = [string]$commit.sha
    if ($revision -notmatch '^[a-f0-9]{40}$') { throw 'GitHub did not return a valid revision.' }
    $tree = Invoke-RestMethod -Uri "$api/git/trees/$($commit.commit.tree.sha)?recursive=1" -Headers $headers
    if ($tree.truncated) { throw 'GitHub returned an incomplete file listing. Ask the team for an offline package.' }
    $app = Join-Path $root "releases\$revision"
    $files = @($tree.tree | Where-Object {
        $_.type -eq 'blob' -and (
            $_.path -match '^(src/|config/|slicer-extension/BranchForge/|slicer-extension/scripts/)' -or
            $_.path -match '^models/(learned_results|learned_2000_results)/(held_out_(19|20|21|22|23)/model\.pt|training_manifest\.json)$' -or
            $_.path -in @('run.py', 'requirements.txt', 'scripts/setup_environment.py', 'scripts/verify_models.py', 'config/models-manifest.json', 'slicer-extension/Launch-BranchForge.ps1')
        )
    })
    if ($files.Count -lt 10) { throw 'The selected revision does not contain the expected application.' }
    foreach ($file in $files) {
        $target = [IO.Path]::GetFullPath((Join-Path $app $file.path))
        if (-not $target.StartsWith($app + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe repository path.' }
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        if ((Test-Path -LiteralPath $target) -and (Get-GitBlobHash $target) -eq $file.sha) { continue }
        Download-File "https://raw.githubusercontent.com/Toastyybread1/toralis-challenge/$revision/$($file.path)" $target
        if ((Get-GitBlobHash $target) -ne $file.sha) { throw "Source integrity check failed: $($file.path)" }
    }

    Write-Host '[2/5] Locating/installing 3D Slicer 5.12.4...'
    $slicer = Join-Path $env:LOCALAPPDATA 'slicer.org\3D Slicer 5.12.4\Slicer.exe'
    if (-not (Test-Path -LiteralPath $slicer)) {
        $installer = Join-Path $cache 'Slicer-5.12.4-win-amd64.exe'
        $expected = '5ba320cb67f0acdaacf0a31380e9cf3b9f46d05f57a53da7e04ebcd9490251ecbe998bfefdbdab1f747e038653177868cdb0ad30986473b9d68efba0f4c6045c'
        if (-not (Test-Path -LiteralPath $installer) -or (Get-FileHash $installer -Algorithm SHA512).Hash -ne $expected) {
            Write-Host 'Downloading Slicer; this large download can take several minutes...'
            Download-File 'https://download.slicer.org/bitstream/6aa1db04ce9de556d30112bb' $installer
        }
        if ((Get-FileHash $installer -Algorithm SHA512).Hash -ne $expected) { throw 'Slicer checksum mismatch. Installer was not executed.' }
        Run-Installer $installer '/S'
        if (-not (Test-Path -LiteralPath $slicer)) { throw "Slicer was not found at $slicer. Install 5.12.4 for the current user, then retry." }
    }

    Write-Host '[3/5] Locating/installing 64-bit Python 3.12...'
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $installer = Join-Path $cache 'python-3.12.10-amd64.exe'
        Download-File 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $installer
        $signature = Get-AuthenticodeSignature -FilePath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
            throw 'Python installer signature could not be verified. Installer was not executed.'
        }
        Run-Installer $installer '/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_pip=1'
    }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Python installation did not finish. Restart Windows and retry.' }
    & $python -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8, 'Python 3.12 x64 required'"
    if ($LASTEXITCODE -ne 0) { throw 'The installed Python is not compatible.' }

    Write-Host '[4/5] Installing and checking detector packages. This may take several minutes...'
    # Prefer wheels: do not attempt slow C/C++ builds on a fresh laptop.
    $oldBinary = $env:PIP_ONLY_BINARY
    try {
        $env:PIP_ONLY_BINARY = ':all:'
        & $python (Join-Path $app 'scripts\setup_environment.py')
        if ($LASTEXITCODE -ne 0) { throw 'Detector setup failed. See the pip error above; do not launch detection yet.' }
    } finally { $env:PIP_ONLY_BINARY = $oldBinary }

    Write-Host '[5/5] Creating the BranchForge desktop shortcut...'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BranchForge.lnk'))
    $shortcut.TargetPath = $slicer
    $shortcut.Arguments = '--no-splash --additional-module-paths "' + (Join-Path $app 'slicer-extension\BranchForge') + '" --python-script "' + (Join-Path $app 'slicer-extension\scripts\launch.py') + '"'
    $shortcut.WorkingDirectory = $app
    $shortcut.IconLocation = "$slicer,0"
    $shortcut.Save()
    Write-Host "READY. Revision: $revision"
    Write-Host 'Open BranchForge from your desktop. Choose Explore synthetic example to try the UI.'
    Write-Host 'For real detection, select your CT and aorta mask, Load study, then Run detection.'
    Write-Host "Pipeline Python: $app\.venv\Scripts\python.exe"
    Write-Host "Pipeline script: $app\run.py"
    if (-not $NoLaunch) {
        # Intentionally visible: the user requested the interactive app.
        Start-Process -FilePath $slicer -ArgumentList $shortcut.Arguments -WorkingDirectory $app
    }
}

# Dot-source for tests without downloading or installing anything.
if ($MyInvocation.InvocationName -ne '.') {
    $log = Join-Path $env:TEMP ('BranchForge-setup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    Start-Transcript -Path $log | Out-Null
    try { Install-BranchForge }
    catch { Write-Host "SETUP STOPPED: $($_.Exception.Message)" -ForegroundColor Red; Write-Host "Share this log with the team: $log"; exit 1 }
    finally { Stop-Transcript | Out-Null }
}
