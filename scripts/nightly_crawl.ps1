# Nightly crawl on the owner's PC (Windows Task Scheduler runs this at 23:00).
#
# - Shops are crawled in priority order: Profihairshop and XpertBeauty first, and from
#   those two only Wella and L'Oreal (incl. Kerastase) products (owner, 2026-10-29);
#   then the other shops, all brands, if time is left.
# - --skip-seen-hours 144: pages collected in the last 6 days are skipped, so a catalogue
#   too big for one night continues the next night, and every product is refreshed about
#   once a week.
# - --until <next 07:00>: stops cleanly between pages in the morning; shops not reached
#   wait for the next night. The date and time are fixed once here, so a second run that
#   starts after 07:00 stops at once instead of going on until the next morning.
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

$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

"=== $(Get-Date -Format s) nightly crawl started" | Out-File -FilePath $log -Append -Encoding utf8
# cmd.exe does the redirection: Windows PowerShell's own `>>` would write UTF-16 and wrap
# every stderr (log) line in an error record. Paths go through environment variables to
# avoid quoting trouble with the spaces in them.
$env:CRAWL_PY = $python
$env:CRAWL_LOG = $log
$until = (Get-Date).Date.AddHours(7)
if ($until -le (Get-Date)) { $until = $until.AddDays(1) }
$common = " --skip-seen-hours 144 --until $($until.ToString('yyyy-MM-ddTHH:mm')) --match --keep-awake"

function Invoke-Crawl([string] $name, [string] $options) {
    $env:CRAWL_REPORT = Join-Path $logs "crawl-$stamp-$name.json"
    "=== $(Get-Date -Format s) $name crawl started" | Out-File -FilePath $log -Append -Encoding utf8
    & cmd.exe /d /c ('"%CRAWL_PY%" -m beautycrawler.crawler -v run' + $options + $common +
        ' --summary-json "%CRAWL_REPORT%" >> "%CRAWL_LOG%" 2>&1')
    "=== $(Get-Date -Format s) $name crawl finished (exit code $LASTEXITCODE)" | Out-File -FilePath $log -Append -Encoding utf8
}

Invoke-Crawl "brands" ' --retailer profihairshop --retailer xpertbeauty --only-brands wella,loreal,kerastase'
Invoke-Crawl "others" ' --retailer parfimo --retailer esteto --retailer probeauty --retailer beautylounge'
