# Mede cold start da Edge Function `primes`.
#
# Estrategia: em cada iteracao faz-se (a) um pedido apos longa espera
# (presumido cold start) e (b) um pedido imediato a seguir (warm),
# para servir de baseline comparavel.
#
# Uso (PowerShell):
#   $env:SUPABASE_URL = "https://uuvyutktcuhpwlltquii.supabase.co/functions/v1/primes"
#   $env:SUPABASE_KEY = "sb_publishable_xxxxx"
#   ./tests/coldstart.ps1                       # default: 15 iteracoes, 900s de espera
#   ./tests/coldstart.ps1 -Iterations 20 -SleepSeconds 1200

param(
    [int]    $Iterations   = 15,
    [int]    $SleepSeconds = 900,    # 15 min: tempo tipico de reciclagem de worker
    [int]    $PrimesN      = 1000,
    [string] $OutFile      = "tests/coldstart.csv"
)

if (-not $env:SUPABASE_URL -or -not $env:SUPABASE_KEY) {
    Write-Error "Define `$env:SUPABASE_URL e `$env:SUPABASE_KEY antes de correr."
    exit 1
}

$headers = @{ 
    "Content-Type"  = "application/json"
    "apikey"        = $env:SUPABASE_KEY
    "Authorization" = "Bearer $($env:SUPABASE_KEY)"
}
$body = (@{ number = $PrimesN } | ConvertTo-Json -Compress)

# Cria ficheiro com cabecalho se nao existir.
if (-not (Test-Path $OutFile)) {
    "timestamp,iteration,kind,latency_ms,status,bytes" | Out-File -FilePath $OutFile -Encoding utf8
}

function Invoke-Probe {
    param([int]$Iter, [string]$Kind)

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest -Uri $env:SUPABASE_URL `
                                  -Method POST `
                                  -Headers $headers `
                                  -Body $body `
                                  -UseBasicParsing `
                                  -TimeoutSec 30
        $sw.Stop()
        $status = [int]$resp.StatusCode
        $bytes  = $resp.RawContentLength
    } catch {
        $sw.Stop()
        $status = -1
        $bytes  = 0
    }
    $ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    $ts = (Get-Date).ToString("o")
    $line = "$ts,$Iter,$Kind,$ms,$status,$bytes"
    Add-Content -Path $OutFile -Value $line
    Write-Host ("[{0}] iter={1} kind={2} {3} ms  status={4}" -f $ts, $Iter, $Kind, $ms, $status)
}

Write-Host "=> $Iterations iteracoes; espera de $SleepSeconds s entre cold starts."
Write-Host "=> Resultados em $OutFile`n"

for ($i = 1; $i -le $Iterations; $i++) {
    if ($i -gt 1) {
        Write-Host "-- A aguardar $SleepSeconds s para induzir cold start (iter $i)..."
        Start-Sleep -Seconds $SleepSeconds
    }
    Invoke-Probe -Iter $i -Kind "cold"
    Start-Sleep -Milliseconds 500
    Invoke-Probe -Iter $i -Kind "warm"
}

Write-Host "`nConcluido."
