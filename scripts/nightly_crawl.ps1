# Nightly crawl on the owner's PC (Windows Task Scheduler runs this at 23:00).
#
# - Shops are crawled in priority order: Profihairshop and XpertBeauty first.
# - --skip-seen-hours 144: pages collected in the last 6 days are skipped, so a catalogue
#   too big for one night continues the next night, and every product is refreshed about
#   once a week.
# - --until 07:00: stops cleanly between pages in the morning; shops not reached wait
#   for the next night.
# - --match links new listings to catalogue products: at the start (anything an interrupted
#   night left), every 5 minutes during the crawl, and at the end.
# - --keep-awake asks Windows not to sleep or turn the screen off until the crawl ends.
# - -v writes a progress line per shop every 5 minutes, so a stopped run shows when.
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
$env:PYTHONUNBUFFERED = "1"

"=== $(Get-Date -Format s) nightly crawl started" | Out-File -FilePath $log -Append -Encoding utf8
# cmd.exe does the redirection: Windows PowerShell's own `>>` would write UTF-16 and wrap
# every stderr (log) line in an error record. Paths go through environment variables to
# avoid quoting trouble with the spaces in them.
$env:CRAWL_PY = $python
$env:CRAWL_LOG = $log
$env:CRAWL_REPORT = $report
$crawl = '"%CRAWL_PY%" -m beautycrawler.crawler -v run' +
    ' --retailer profihairshop --retailer xpertbeauty --retailer parfimo' +
    ' --retailer esteto --retailer probeauty --retailer beautylounge' +
    ' --skip-seen-hours 144 --until 07:00 --match --keep-awake' +
    ' --summary-json "%CRAWL_REPORT%" >> "%CRAWL_LOG%" 2>&1'
& cmd.exe /d /c $crawl
"=== $(Get-Date -Format s) nightly crawl finished (exit code $LASTEXITCODE)" | Out-File -FilePath $log -Append -Encoding utf8
