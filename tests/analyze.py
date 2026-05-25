"""
Analise dos resultados de carga e cold start da Edge Function `primes`.

Le:
  - tests/load.json    (output de `k6 run --out json=tests/load.json`)
  - tests/coldstart.csv (output de tests/coldstart.ps1)

Gera:
  - tests/out/stats.txt
  - tests/out/latency_sequential.png
  - tests/out/latency_concurrent.png
  - tests/out/latency_stages.png
  - tests/out/cold_start.png

Uso:
  pip install pandas matplotlib numpy
  python tests/analyze.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT       = Path(__file__).resolve().parent
LOAD_JSON  = ROOT / "load.json"
COLD_CSV   = ROOT / "coldstart.csv"
OUT_DIR    = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)

PERCENTILES = [50, 90, 95, 99]


def load_k6(path: Path) -> pd.DataFrame:
    """Le o JSON-lines do k6 e devolve apenas as metricas http_req_duration."""
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "Point":
                continue
            if obj.get("metric") != "http_req_duration":
                continue
            tags = obj.get("data", {}).get("tags", {}) or {}
            rows.append({
                "time":     obj["data"]["time"],
                "value_ms": obj["data"]["value"],
                "scenario": tags.get("scenario", "unknown"),
                "vus":      int(tags.get("vu", 0)) if tags.get("vu") else None,
                "status":   tags.get("status"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df


def summarize(series: pd.Series) -> dict:
    return {
        "n":      int(series.size),
        "min":    float(series.min()),
        "max":    float(series.max()),
        "mean":   float(series.mean()),
        "median": float(series.median()),
        **{f"p{p}": float(np.percentile(series, p)) for p in PERCENTILES},
    }


def fmt(stats: dict) -> str:
    keys = ["n", "min", "mean", "median", "p90", "p95", "p99", "max"]
    return "  ".join(f"{k}={stats[k]:.2f}" if isinstance(stats[k], float) else f"{k}={stats[k]}" for k in keys)


def plot_hist(series: pd.Series, title: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.hist(series, bins=60, color="#4C72B0", edgecolor="white")
    for p, c in zip([50, 95, 99], ["#2ca02c", "#ff7f0e", "#d62728"]):
        v = np.percentile(series, p)
        ax.axvline(v, color=c, linestyle="--", linewidth=1.2, label=f"p{p}={v:.0f} ms")
    ax.set_xlabel("Latência (ms)")
    ax.set_ylabel("Frequência")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# Stages do cenario concorrente em load.js (duracao acumulada em segundos
# a partir do arranque do cenario, e respetivo VU target no final do stage).
STAGES = [
    (0,   30,  "1 -> 5"),
    (30,  60,  "5 -> 10"),
    (60,  90,  "10 -> 25"),
    (90,  120, "25 -> 50"),
    (120, 150, "50 -> 100"),
    (150, 180, "100 -> 0"),
]


def per_stage_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega latencias do cenario concorrente por stage da rampa de VUs."""
    df = df.copy().sort_values("time")
    t0 = df["time"].min()
    df["t_rel"] = (df["time"] - t0).dt.total_seconds()
    rows = []
    for start, end, label in STAGES:
        s = df.loc[(df["t_rel"] >= start) & (df["t_rel"] < end), "value_ms"]
        if s.empty:
            continue
        rows.append({
            "stage":  label,
            "t_ini":  start,
            "n":      int(s.size),
            "mean":   float(s.mean()),
            "median": float(s.median()),
            "p90":    float(np.percentile(s, 90)),
            "p95":    float(np.percentile(s, 95)),
            "p99":    float(np.percentile(s, 99)),
            "max":    float(s.max()),
        })
    return pd.DataFrame(rows)


def plot_concurrent(df: pd.DataFrame, out: Path) -> None:
    # Linha temporal (janelas de 5s) com percentis ao longo da rampa.
    df = df.copy().sort_values("time")
    df["bucket"] = df["time"].dt.floor("5s")
    agg = df.groupby("bucket")["value_ms"].agg(
        p50=lambda s: np.percentile(s, 50),
        p95=lambda s: np.percentile(s, 95),
        p99=lambda s: np.percentile(s, 99),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(agg["bucket"], agg["p50"], label="p50", color="#2ca02c")
    ax.plot(agg["bucket"], agg["p95"], label="p95", color="#ff7f0e")
    ax.plot(agg["bucket"], agg["p99"], label="p99", color="#d62728")

    # Sobreposicao das fronteiras dos stages para leitura imediata.
    t0 = df["time"].min()
    for start, _end, label in STAGES:
        x = t0 + pd.Timedelta(seconds=start)
        ax.axvline(x, color="black", alpha=0.15, linestyle=":")
        ax.text(x, ax.get_ylim()[1] * 0.95, " " + label,
                fontsize=7, color="black", alpha=0.55, rotation=90, va="top")

    ax.set_xlabel("Tempo")
    ax.set_ylabel("Latência (ms)")
    ax.set_title("Latência vs. tempo durante rampa de concorrência")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_stage_bars(stats: pd.DataFrame, out: Path) -> None:
    """Barras agrupadas: p50/p95/p99 por stage da rampa de VUs."""
    fig, ax = plt.subplots(figsize=(7, 3.8))
    x = np.arange(len(stats))
    w = 0.27
    ax.bar(x - w, stats["median"], w, label="p50", color="#2ca02c")
    ax.bar(x,     stats["p95"],    w, label="p95", color="#ff7f0e")
    ax.bar(x + w, stats["p99"],    w, label="p99", color="#d62728")
    ax.set_xticks(x)
    ax.set_xticklabels(stats["stage"], rotation=0, fontsize=8)
    ax.set_xlabel("Stage (VUs alvo)")
    ax.set_ylabel("Latência (ms)")
    ax.set_title("Latência por stage da rampa de concorrência")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_cold(df: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = df["iteration"]
    cold = df[df["kind"] == "cold"]
    warm = df[df["kind"] == "warm"]
    ax.bar(cold["iteration"] - 0.18, cold["latency_ms"], width=0.36,
           label="cold", color="#d62728")
    ax.bar(warm["iteration"] + 0.18, warm["latency_ms"], width=0.36,
           label="warm", color="#2ca02c")
    ax.set_xlabel("Iteração")
    ax.set_ylabel("Latência (ms)")
    ax.set_title("Cold start vs. warm (pedido imediatamente a seguir)")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main() -> None:
    lines: list[str] = []

    # ---------- k6 ----------
    if LOAD_JSON.exists():
        df = load_k6(LOAD_JSON)
        if df.empty:
            lines.append("[load.json] sem pontos http_req_duration.")
        else:
            seq  = df[df["scenario"] == "sequential"]["value_ms"]
            conc = df[df["scenario"] == "concurrent"]["value_ms"]

            if not seq.empty:
                s = summarize(seq)
                lines.append("=== Latencia sequencial (1 VU, warm) ===")
                lines.append(fmt(s))
                plot_hist(seq, "Latência sequencial (1 VU)", OUT_DIR / "latency_sequential.png")

            if not conc.empty:
                s = summarize(conc)
                lines.append("")
                lines.append("=== Latencia concorrente (rampa 1->100 VUs) ===")
                lines.append(fmt(s))
                conc_df = df[df["scenario"] == "concurrent"]
                plot_concurrent(conc_df, OUT_DIR / "latency_concurrent.png")

                stage_stats = per_stage_stats(conc_df)
                if not stage_stats.empty:
                    stage_stats.to_csv(OUT_DIR / "stages.csv", index=False)
                    plot_stage_bars(stage_stats, OUT_DIR / "latency_stages.png")
                    lines.append("")
                    lines.append("--- por stage (VU target) ---")
                    header = f"{'stage':<12}{'n':>7}{'mean':>9}{'p50':>8}{'p90':>8}{'p95':>8}{'p99':>9}{'max':>10}"
                    lines.append(header)
                    for _, r in stage_stats.iterrows():
                        lines.append(
                            f"{r['stage']:<12}{int(r['n']):>7}"
                            f"{r['mean']:>9.1f}{r['median']:>8.1f}"
                            f"{r['p90']:>8.1f}{r['p95']:>8.1f}"
                            f"{r['p99']:>9.1f}{r['max']:>10.1f}"
                        )
    else:
        lines.append(f"[aviso] {LOAD_JSON} nao encontrado; corre k6 primeiro.")

    # ---------- cold start ----------
    if COLD_CSV.exists():
        cold_df = pd.read_csv(COLD_CSV)
        cold = cold_df[cold_df["kind"] == "cold"]["latency_ms"]
        warm = cold_df[cold_df["kind"] == "warm"]["latency_ms"]
        if not cold.empty:
            lines.append("")
            lines.append("=== Cold start ===")
            lines.append(fmt(summarize(cold)))
        if not warm.empty:
            lines.append("=== Warm (post cold) ===")
            lines.append(fmt(summarize(warm)))
        if not cold.empty and not warm.empty:
            ratio = cold.mean() / warm.mean()
            lines.append(f"penalidade media cold/warm: {ratio:.2f}x")
            plot_cold(cold_df, OUT_DIR / "cold_start.png")
    else:
        lines.append(f"[aviso] {COLD_CSV} nao encontrado; corre coldstart.ps1 primeiro.")

    report = "\n".join(lines) + "\n"
    (OUT_DIR / "stats.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
