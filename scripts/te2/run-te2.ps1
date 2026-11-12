<#
.SYNOPSIS
    Runs Tabular Editor 2 CLI read-only against a PBIP SemanticModel definition folder
    to execute Best Practice Analyzer (-AX -G) and extract TOM metadata + DAX DependsOn (-S).
#>
[CmdletBinding()]
param(
    [string]$ModelDefinitionPath = "",
    [string]$RulesPath = "config\bpa-rules.json",
    [string]$OutDir = "dist",
    [string]$Te2Exe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $RepoRoot
try {
    if ([string]::IsNullOrWhiteSpace($ModelDefinitionPath)) {
        $pbip = Get-ChildItem -Path $RepoRoot -Filter "*.pbip" | Select-Object -First 1
        if (-not $pbip) {
            throw "No .pbip file found in repository root: $RepoRoot"
        }
        $smDir = Join-Path $RepoRoot ($pbip.BaseName + ".SemanticModel\definition")
        if (-not (Test-Path $smDir)) {
            throw "SemanticModel definition folder not found: $smDir"
        }
        $ModelDefinitionPath = $smDir
    }

    if (-not (Test-Path $OutDir)) {
        New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
    }
    $OutDirAbs = (Resolve-Path $OutDir).Path
    $RulesAbs = (Resolve-Path $RulesPath).Path
    $ScriptAbs = (Resolve-Path (Join-Path $PSScriptRoot "extract-model-metadata.csx")).Path

    # Locate TabularEditor.exe (explicit override, system install, or CI portable cache)
    $candidates = @(
        $Te2Exe,
        "C:\Program Files (x86)\Tabular Editor\TabularEditor.exe",
        "C:\Program Files\Tabular Editor\TabularEditor.exe",
        (Join-Path $RepoRoot "tools\te2\TabularEditor.exe")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $te2ExeResolved = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    $te2Exe = $te2ExeResolved

    if (-not $te2Exe) {
        Write-Host "TabularEditor.exe not found locally. Downloading TabularEditor.Portable.zip..."
        $te2Dir = Join-Path $RepoRoot "tools\te2"
        New-Item -ItemType Directory -Path $te2Dir -Force | Out-Null
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/TabularEditor/TabularEditor/releases/latest"
        $asset = $release.assets | Where-Object { $_.name -match "TabularEditor\.Portable\.zip$" } | Select-Object -First 1
        if (-not $asset) {
            throw "Could not find TabularEditor.Portable.zip in latest GitHub release."
        }
        $zipPath = Join-Path $te2Dir "TabularEditor.Portable.zip"
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $te2Dir -Force
        Remove-Item $zipPath -Force
        $te2Exe = Join-Path $te2Dir "TabularEditor.exe"
        if (-not (Test-Path $te2Exe)) {
            throw "TabularEditor.exe missing after extracting portable archive."
        }
    }

    function Invoke-TE2 {
        param(
            [string[]]$Arguments,
            [string]$StdoutPath,
            [string]$StderrPath
        )
        $quotedArgs = ($Arguments | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }) -join ' '
        $proc = Start-Process -FilePath $te2Exe -ArgumentList $quotedArgs -Wait -NoNewWindow -PassThru `
            -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
        return $proc.ExitCode
    }

    $bpaStdout = Join-Path $OutDirAbs "te2-bpa.txt"
    $bpaStderr = Join-Path $OutDirAbs "te2-bpa.err.txt"
    Write-Host "Running TE2 BPA (-AX -G) on $ModelDefinitionPath..."
    $bpaExit = Invoke-TE2 -Arguments @($ModelDefinitionPath, "-AX", $RulesAbs, "-G") -StdoutPath $bpaStdout -StderrPath $bpaStderr
    Write-Host "TE2 BPA exit code: $bpaExit"

    $metaOut = Join-Path $OutDirAbs "te2-metadata.json"
    $env:TE2_METADATA_OUT = $metaOut
    $metaStdout = Join-Path $OutDirAbs "te2-meta.txt"
    $metaStderr = Join-Path $OutDirAbs "te2-meta.err.txt"
    Write-Host "Running TE2 TOM metadata extraction (-S)..."
    $metaExit = Invoke-TE2 -Arguments @($ModelDefinitionPath, "-S", $ScriptAbs) -StdoutPath $metaStdout -StderrPath $metaStderr
    if ($metaExit -ne 0) {
        $errText = if (Test-Path $metaStderr) { Get-Content $metaStderr -Raw } else { "" }
        $outText = if (Test-Path $metaStdout) { Get-Content $metaStdout -Raw } else { "" }
        throw "TE2 metadata extraction failed with exit code $metaExit.`nSTDOUT: $outText`nSTDERR: $errText"
    }

    $bpaOutput = if (Test-Path $bpaStdout) { Get-Content $bpaStdout -Raw } else { "" }
    if ($bpaOutput -match "Error on rule") {
        throw "TE2 reported rule syntax/evaluation error(s) in $bpaStdout"
    }

    Write-Host "TE2 extraction complete: $bpaStdout, $metaOut"
}
finally {
    Pop-Location
}
