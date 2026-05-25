// k6 load test para a Edge Function `primes` do Supabase.
//
// Corre dois cenarios em sequencia:
//   1. sequential -> 1 VU, 1000 iteracoes (latencia "limpa", funcao quente).
//   2. concurrent -> rampa 1 -> 5 -> 10 -> 25 -> 50 -> 100 VUs (latencia sob carga).
//
// Uso (PowerShell):
//   $env:SUPABASE_URL = "https://uuvyutktcuhpwlltquii.supabase.co/functions/v1/primes"
//   $env:SUPABASE_KEY = "sb_publishable_xxxxx"
//   k6 run --out json=tests/load.json tests/load.js

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const URL = __ENV.SUPABASE_URL;
const KEY = __ENV.SUPABASE_KEY;
const N   = Number(__ENV.PRIMES_N || 1000); // valor de `n` enviado a funcao

if (!URL || !KEY) {
  throw new Error("Define SUPABASE_URL e SUPABASE_KEY antes de correr o teste.");
}

const seqLatency  = new Trend("latency_sequential_ms", true);
const concLatency = new Trend("latency_concurrent_ms", true);

export const options = {
  // Aborta o teste se mais de 1% dos pedidos falharem.
  thresholds: {
    http_req_failed: ["rate<0.01"],
  },
  scenarios: {
    sequential: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1000,
      maxDuration: "10m",
      exec: "sequential",
      tags: { scenario: "sequential" },
    },
    concurrent: {
      executor: "ramping-vus",
      startVUs: 1,
      // Arranca alguns segundos depois do sequencial para nao se sobreporem.
      startTime: "10s",
      stages: [
        { duration: "30s", target: 5   },
        { duration: "30s", target: 10  },
        { duration: "30s", target: 25  },
        { duration: "30s", target: 50  },
        { duration: "30s", target: 100 },
        { duration: "30s", target: 0   },
      ],
      exec: "concurrent",
      tags: { scenario: "concurrent" },
    },
  },
};

const params = {
  headers: {
    "Content-Type": "application/json",
    "apikey": KEY,
    "Authorization": `Bearer ${KEY}`,
  },
  tags: { name: "primes" },
};

const payload = JSON.stringify({ number: N });

function invoke(trend) {
  const res = http.post(URL, payload, params);
  trend.add(res.timings.duration);
  check(res, {
    "status 200": (r) => r.status === 200,
    "tem campo primes": (r) => {
      try { return Array.isArray(r.json("primes")); } catch (_) { return false; }
    },
  });
}

export function sequential() { invoke(seqLatency); }
export function concurrent() { invoke(concLatency); }
