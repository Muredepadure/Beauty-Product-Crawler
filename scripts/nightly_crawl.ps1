# Nightly crawl on the owner's PC (Windows Task Scheduler runs this at 23:00).
#
# - Shops are crawled in priority order: Profihairshop and XpertBeauty first.
# - --skip-seen-hours 144: pages collected in the last 6 days are skipped, so a catalogue
#   too big for one night continues the next night, and every product is refreshed about
#   once a week.
# - --until 07:00: stops cleanly between pages in the morning; shops not reached wait
#   for the next night.
# - --match links new listings to catalogue products after the crawl.
# Logs and run reports go to logs\ (git-ignored), one file per night.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logs "crawl-$stamp.log"
$report = Join-Path $logs "crawl-$stamp.json"

$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

"=== $(Get-Date -Format s) nightly crawl started" | Out-File -FilePath $log -Append -Encoding utf8
& $python -m beautycrawler.crawler run `
    --retailer profihairshop `
    --retailer xpertbeauty `
    --retailer parfimo `
    --retailer esteto `
    --retailer probeauty `
    --retailer beautylounge `
    --skip-seen-hours 144 `
    --until 07:00 `
    --match `
    --summary-json $report *>> $log
"=== $(Get-Date -Format s) nightly crawl finished (exit code $LASTEXITCODE)" | Out-File -FilePath $log -Append -Encoding utf8
