<#
.SYNOPSIS
    Analyze one or all reports/<ticket> PBIP projects without modifying source definitions.
#>
[CmdletBinding()]
param(
    [string]$Ticket = "",
    [switch]$SkipTe2,
    [switch]$EnforceGate,
    [switch]$OpenHtml,
    [string]$Te2Exe = "",
    [string]$Dist = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = "python" }
$OriginalPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Join-Path $RepoRoot "scripts") + [IO.Path]::PathSeparator + $OriginalPythonPath
Push-Location $RepoRoot
try {
    $CommonArgs = @("-m", "pbi_cicd.cli", "--root", $RepoRoot)
    if ($Dist) { $CommonArgs += @("--dist", $Dist) }
    $SelectionArgs = @()
    if ($Ticket) { $SelectionArgs += @("--ticket", $Ticket) }
    $ProjectsJson = & $PythonExe @CommonArgs @SelectionArgs --list-projects
    if ($LASTEXITCODE -ne 0) { throw "Ticket discovery failed" }
    $Projects = @($ProjectsJson | ConvertFrom-Json)
    if (-not $SkipTe2) {
        foreach ($Project in $Projects) {
            Write-Host "Extracting TE2 metadata for $($Project.ticket)..."
            $RunnerArgs = @{
                ModelDefinitionPath = Join-Path $Project.semantic_model_dir "definition"
                RulesPath = $Project.rules_file
                OutDir = $Project.dist_dir
            }
            if ($Te2Exe) { $RunnerArgs.Te2Exe = $Te2Exe }
            elseif ($env:TE2_EXE) { $RunnerArgs.Te2Exe = $env:TE2_EXE }
            & (Join-Path $PSScriptRoot "te2\run-te2.ps1") @RunnerArgs
            & $PythonExe @CommonArgs --ticket $Project.ticket --record-te2-source
            if ($LASTEXITCODE -ne 0) { throw "TE2 provenance recording failed for $($Project.ticket)" }
        }
    }
    $AnalysisArgs = $CommonArgs + $SelectionArgs
    if (-not $SkipTe2) { $AnalysisArgs += "--require-te2" }
    if ($EnforceGate) { $AnalysisArgs += "--enforce-gate" }
    & $PythonExe @AnalysisArgs
    $ResultCode = $LASTEXITCODE
    if ($OpenHtml -and $ResultCode -lt 2) {
        if ($Ticket -and $Projects.Count -eq 1) { $HtmlPath = Join-Path $Projects[0].dist_dir "index.html" }
        else {
            $OutputBase = if ($Dist) { $Dist } else { (Get-Content "config\cicd-config.json" -Raw | ConvertFrom-Json).output.dist_dir }
            $HtmlPath = Join-Path $OutputBase "index.html"
        }
        Start-Process -FilePath $HtmlPath
    }
    exit $ResultCode
}
finally {
    Pop-Location
    $env:PYTHONPATH = $OriginalPythonPath
}
