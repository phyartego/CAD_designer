function Install-LocalCodex {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Root)

    $ErrorActionPreference = "Stop"
    $version = "0.170.0"
    $target = "x86_64-pc-windows-msvc"
    $entrypoint = "codex-$target.exe"
    $checksum = "B1634415B6ECB87FEA80691580DFE49F83FD46F0AD93F128BA029604D7FAA158"
    $url = "https://github.com/openai/codex/releases/download/rust-v$version/$entrypoint.zip"
    $local = Join-Path $Root ".local"
    $destination = Join-Path $local "codex"

    function Test-CodexBundle([string]$Directory) {
        foreach ($file in @($entrypoint, "codex-package.json", "codex-code-mode-host.exe",
                "bin/codex-exec-server.exe", "codex-path/rg.exe", "codex-resources/codex-command-runner.exe",
                "codex-resources/codex-windows-sandbox-setup.exe")) {
            if (-not (Test-Path -LiteralPath (Join-Path $Directory $file) -PathType Leaf)) { return $false }
        }
        $metadata = Get-Content -Raw -LiteralPath (Join-Path $Directory "codex-package.json") | ConvertFrom-Json
        if ($metadata.version -ne $version -or $metadata.target -ne $target -or $metadata.entrypoint -ne $entrypoint) {
            return $false
        }
        $cli = Join-Path $Directory $entrypoint
        $reported = & $cli --version
        return ($LASTEXITCODE -eq 0 -and ($reported -contains "codex-cli $version"))
    }

    if (Test-Path -LiteralPath $destination) {
        try {
            if (Test-CodexBundle $destination) {
                Write-Host "Using project-local Codex CLI $version."
                return
            }
        } catch { Write-Verbose "The existing local Codex package needs repair: $_" }
    } else {
        $existing = Get-Command codex -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($existing) {
            try {
                $reported = & $existing.Source --version
                if ($LASTEXITCODE -eq 0 -and ($reported -match 'codex-cli [0-9]')) {
                    Write-Host "Using $reported from $($existing.Source)."
                    return
                }
            } catch { Write-Verbose "Codex on PATH failed its version check: $_" }
        }
    }

    [IO.Directory]::CreateDirectory($local) | Out-Null
    $staging = Join-Path $local ("install-codex-" + [Guid]::NewGuid())
    $expanded = Join-Path $staging "package"
    $backup = Join-Path $staging "previous"
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    try {
        $ProgressPreference = "SilentlyContinue"
        $archive = Join-Path $staging "codex.zip"
        Write-Host "Downloading the official Windows x64 Codex CLI $version (205 MiB)."
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $checksum) {
            throw "Codex release ZIP failed SHA256 verification."
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $expanded
        if (-not (Test-CodexBundle $expanded)) {
            throw "Codex native bundle failed its package metadata, helper or --version check."
        }
        if (Test-Path -LiteralPath $destination) {
            [IO.Directory]::Move($destination, $backup)
        }
        try { [IO.Directory]::Move($expanded, $destination) }
        catch {
            if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $destination)) {
                [IO.Directory]::Move($backup, $destination)
            }
            throw
        }
        Write-Host "Installed Codex CLI $version for this checkout."
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -Recurse -Force -LiteralPath $staging }
    }
}
