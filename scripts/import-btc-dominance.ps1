param(
    [string]$CsvPath = "backend/data/btc_dominance/bitcoin-dominance-day-data-1-year-tokeninsight-dashboard.csv"
)

$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\backend"
try {
    python -m app.scripts.import_btc_dominance --csv-path "..\$CsvPath"
}
finally {
    Pop-Location
}
