[CmdletBinding()]
param (
    [switch]$SkipFreeCAD,
    [switch]$SkipDemo
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

function Install-CadDependency([string]$Id) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install --id $Id --exact --source winget --architecture x64 --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) { return }
        $exitCode = $LASTEXITCODE
        # Some winget versions report a failure for an already installed package.
        if ($Id -eq "Python.Python.3.12" -and (Find-ProjectPython)) { return }
        if ($Id -eq "FreeCAD.FreeCAD" -and (Find-FreeCADCmd)) { return }
        Write-Host "winget returned $exitCode for $Id; trying its verified upstream installer."
    }

    # Store-less Windows installations. Checksums match Microsoft's winget manifests.
    if ($Id -eq "Python.Python.3.12") {
        $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
        $digest = "67B5635E80EA51072B87941312D00EC8927C4DB9BA18938F7AD2D27B328B95FB"
        $flags = @("/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0")
    } elseif ($Id -eq "FreeCAD.FreeCAD") {
        $url = "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.2/FreeCAD_1.1.2-Windows-x86_64-py311-installer.exe"
        $digest = "A5D9D829C10A6074620DC4CA52CA13E71D87D866E0CAF4B737172FFB4F94BEC9"
        $flags = @("/S", "/CurrentUser")
    } else {
        throw "Unknown dependency: $Id"
    }
    $installer = Join-Path ([IO.Path]::GetTempPath()) ("consumer-cad-" + [Guid]::NewGuid() + ".exe")
    try {
        $ProgressPreference = "SilentlyContinue"
        Write-Host "Downloading $Id from its official release site."
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash -ne $digest) {
            throw "Downloaded $Id failed SHA256 verification."
        }
        $process = Start-Process -FilePath $installer -ArgumentList $flags -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "$Id installer failed with exit code $($process.ExitCode)" }
    } finally {
        if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer }
    }
}

function Find-ProjectPython {
    $candidates = @()
    foreach ($name in @("python", "python3")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source -notlike "*\Microsoft\WindowsApps\*") {
            $candidates += $found.Source
        }
    }
    foreach ($tag in @("312", "311")) {
        $candidates += "$env:LocalAppData\Programs\Python\Python$tag\python.exe"
        $candidates += "$env:ProgramFiles\Python$tag\python.exe"
    }
    foreach ($scope in @("HKCU:", "HKLM:")) {
        foreach ($version in @("3.12", "3.11")) {
            $key = "$scope\SOFTWARE\Python\PythonCore\$version\InstallPath"
            if (Test-Path -LiteralPath $key) {
                $install = (Get-Item -LiteralPath $key).GetValue("")
                if ($install) { $candidates += Join-Path $install "python.exe" }
            }
        }
    }
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            & $path -c "import sys,struct;sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,12) and struct.calcsize('P')==8 else 1)"
            if ($LASTEXITCODE -eq 0) { return $path }
        }
    }
    return $null
}

function Find-FreeCADCmd {
    if ($env:FREECAD_CMD) {
        if (Test-Path -LiteralPath $env:FREECAD_CMD -PathType Leaf) {
            return (Resolve-Path -LiteralPath $env:FREECAD_CMD).Path
        }
        throw "FREECAD_CMD does not point to an existing executable."
    }
    $app = Get-Command FreeCADCmd.exe -ErrorAction SilentlyContinue
    if ($app) { return $app.Source }
    foreach ($base in @("$env:LOCALAPPDATA\Programs", "$env:LOCALAPPDATA", "$env:ProgramFiles")) {
        $found = Get-ChildItem -Path "$base\FreeCAD*\bin\FreeCADCmd.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Find-ProjectPython
    if (-not $python) {
        Install-CadDependency "Python.Python.3.12"
        $python = Find-ProjectPython
        if (-not $python) { throw "Could not find a 64-bit Python 3.12 after installation." }
    }
    Invoke-Checked $python @("-m", "venv", ".venv")
}
Invoke-Checked $venvPython @("-c", "import sys,struct; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,12) and struct.calcsize('P')==8 else 'Expected a 64-bit Python 3.11 or 3.12 in .venv')")
Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $venvPython @("-m", "pip", "install", "-e", ".")
if (-not $SkipFreeCAD) {
    $cmdPath = Find-FreeCADCmd
    if (-not $cmdPath) {
        Install-CadDependency "FreeCAD.FreeCAD"
        $cmdPath = Find-FreeCADCmd
        if (-not $cmdPath) { throw "Set FREECAD_CMD to FreeCADCmd.exe and rerun." }
    }
    $env:FREECAD_CMD = $cmdPath
}
Invoke-Checked $venvPython @("scripts/configure_agent.py")
$cad = Join-Path $repoRoot ".venv\Scripts\consumer-cad.exe"
Invoke-Checked $cad @("doctor")
if (-not $SkipDemo) {
    $runDir = Join-Path $repoRoot (".local\first-run\" + [guid]::NewGuid().ToString("N"))
    $mode = if ($SkipFreeCAD) { "--no-freecad" } else { "--freecad" }
    Invoke-Checked $cad @("demo", "--out", $runDir, $mode)
    if (-not $SkipFreeCAD -and -not (Get-ChildItem -LiteralPath $runDir -Recurse -Filter "*.FCStd")) {
        throw "The demo produced no FreeCAD document in $runDir"
    }
    Write-Host "Demo output: $runDir"
}
Write-Host "Ready. Import .mcp.json (or .local\mcp.json) and skills\consumer-cad\SKILL.md into WorkBuddy or any MCP client."
