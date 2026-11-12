param([string]$FilePath)
$Tokens = $null
$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($FilePath, [ref]$Tokens, [ref]$Errors) | Out-Null
foreach ($Item in $Errors) { Write-Output $Item.Message }
if ($Errors.Count -gt 0) { exit 1 }
