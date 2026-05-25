# Testes de desempenho — Edge Function `primes`

Três medições, todas automatizadas.

## Pré-requisitos (uma vez)

```powershell
winget install k6
winget install Python.Python.3.12      # se ainda nao tiveres
pip install pandas matplotlib numpy
```

## Variáveis de ambiente

```powershell
$env:SUPABASE_URL = "https://uuvyutktcuhpwlltquii.supabase.co/functions/v1/primes"
$env:SUPABASE_KEY = "sb_publishable_xxxxx"     # publishable key do projeto
```

## 1+2. Latência sequencial e concorrente (k6)

```powershell
k6 run --out json=tests/load.json tests/load.js
```

Dura ~5 min. Gera `tests/load.json` com todos os pontos.
Variável opcional: `$env:PRIMES_N = "10000"` (default 1000).

## 3. Cold start (PowerShell)

```powershell
./tests/coldstart.ps1                          # 15 iter, 900s entre cada
./tests/coldstart.ps1 -Iterations 20 -SleepSeconds 1200
```

Dura horas de relógio (15 × 15 min ≈ 4 h). Deixa correr em background.
Gera `tests/coldstart.csv` em modo *append* — podes interromper e retomar.

## Análise e gráficos

```powershell
python tests/analyze.py
```

Produz em `tests/out/`:
- `stats.txt` — médias, percentis (p50/p90/p95/p99), min/max para cada cenário.
- `latency_sequential.png` — histograma da latência *warm*.
- `latency_concurrent.png` — p50/p95/p99 ao longo da rampa de VUs.
- `latency_stages.png` — barras p50/p95/p99 por *stage* da rampa.
- `cold_start.png` — barras *cold* vs *warm* por iteração.

As imagens entram diretamente no relatório com `\includegraphics{}`.
