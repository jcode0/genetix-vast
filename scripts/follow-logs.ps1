param(
    [Parameter(Mandatory=$true)] [int] $InstanceId,
    [int] $Interval = 5,
    [int] $Tail = 500,
    [string] $Filter = ""
)

# Реал-тайм follow логов vastai (нет native --follow, эмулируем polling).
# Использование:
#   .\scripts\follow-logs.ps1 -InstanceId 37333615
#   .\scripts\follow-logs.ps1 -InstanceId 37333615 -Filter "provision"
#   .\scripts\follow-logs.ps1 -InstanceId 37333615 -Interval 3

$seen = ""
Write-Host "Follow logs for instance $InstanceId (Ctrl+C для выхода)" -ForegroundColor Cyan

while ($true) {
    try {
        $args = @("logs", "$InstanceId", "--tail", "$Tail")
        if ($Filter) { $args += @("--filter", $Filter) }
        $now = (& vastai @args 2>&1 | Out-String)

        if ($now.Length -gt 0) {
            if ($now.StartsWith($seen)) {
                $new = $now.Substring($seen.Length)
            } else {
                Clear-Host
                $new = $now
            }
            if ($new) {
                Write-Host -NoNewline $new
            }
            $seen = $now
        }
    } catch {
        Write-Host "Ошибка: $_" -ForegroundColor Yellow
    }

    Start-Sleep -Seconds $Interval
}
