param(
  [int[]]$Years = @(((Get-Date).Year - 3)..((Get-Date).Year)),
  [switch]$Refresh
)

$ErrorActionPreference = "Stop"
$yearArgs = $Years | ForEach-Object { $_.ToString() }
$syncArgs = @("-m", "pipeline", "sync", "--years") + $yearArgs
if ($Refresh) { $syncArgs += "--refresh" }
python @syncArgs
$officialArgs = @("-m", "pipeline", "enrich-official", "--years") + $yearArgs + @("--venues", "usenix", "ndss", "ccs", "--discover", "--prune-discovered", "--details")
if ($Refresh) { $officialArgs += "--refresh" }
python @officialArgs
python -m pipeline enrich
$titleArgs = @("-m", "pipeline", "enrich-titles", "--years") + $yearArgs + @("--venues", "usenix", "ccs")
python @titleArgs
$sessionArgs = @("-m", "pipeline", "enrich-sessions", "--years") + $yearArgs
if ($Refresh) { $sessionArgs += "--refresh" }
python @sessionArgs
python -m pipeline analyze --provider rules --only-pending
python -m pipeline export --format web --output public/catalog.json
Write-Host "SecAtlas catalog updated." -ForegroundColor Green




