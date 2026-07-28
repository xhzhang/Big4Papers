param(
  [int[]]$Years = @(2023, 2024, 2025, 2026),
  [switch]$Refresh
)

$ErrorActionPreference = "Stop"
$syncArgs = @("-m", "pipeline", "sync", "--years") + ($Years | ForEach-Object { $_.ToString() })
if ($Refresh) { $syncArgs += "--refresh" }
python @syncArgs
python -m pipeline enrich-official --years 2026 --venues usenix ndss --discover --details
python -m pipeline enrich
python -m pipeline enrich-official --years 2023 2024 2025 --details
python -m pipeline enrich-titles --priority-only
$sessionArgs = @("-m", "pipeline", "enrich-sessions", "--years") + ($Years | ForEach-Object { $_.ToString() })
if ($Refresh) { $sessionArgs += "--refresh" }
python @sessionArgs
python -m pipeline analyze --provider rules
python -m pipeline export --format web --output public/catalog.json
Write-Host "SecAtlas catalog updated." -ForegroundColor Green




