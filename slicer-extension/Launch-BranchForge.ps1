param([string]$SlicerPath)
$ErrorActionPreference = 'Stop'
if (-not $SlicerPath) {
    $installRoot = Join-Path $env:LOCALAPPDATA 'slicer.org'
    $slicerCandidates = Get-ChildItem -LiteralPath $installRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like '3D Slicer *' } |
        Sort-Object LastWriteTime -Descending
    foreach ($candidate in $slicerCandidates) {
        $candidateExe = Join-Path $candidate.FullName 'Slicer.exe'
        if (Test-Path -LiteralPath $candidateExe -PathType Leaf) {
            $SlicerPath = $candidateExe
            break
        }
    }
}
if (-not $SlicerPath -or -not (Test-Path -LiteralPath $SlicerPath -PathType Leaf)) {
    throw 'Slicer was not found. Run with -SlicerPath "C:\path\to\Slicer.exe".'
}
$moduleDir = Join-Path $PSScriptRoot 'BranchForge'
$startupScript = Join-Path $PSScriptRoot 'scripts\launch.py'
$slicerArguments = @('--no-splash', '--additional-module-paths', ('"' + $moduleDir + '"'), '--python-script', ('"' + $startupScript + '"'))
# User launcher: intentionally opens the interactive workspace in a new Slicer window.
Start-Process -FilePath $SlicerPath -ArgumentList $slicerArguments

