import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";

// Crivo de Eratóstenes: devolve todos os primos <= n.
function primesUpTo(n: number): number[] {
  if (n < 2) return [];
  const sieve = new Uint8Array(n + 1);
  const primes: number[] = [];
  for (let i = 2; i <= n; i++) {
    if (!sieve[i]) {
      primes.push(i);
      for (let j = i * i; j <= n; j += i) sieve[j] = 1;
    }
  }
  return primes;
}

export default {
  fetch: withSupabase({ auth: ["publishable", "secret"] }, async (req) => {
    const { number } = await req.json();

    if (typeof number !== "number" || !Number.isInteger(number) || number < 0) {
      return Response.json(
        { error: "Envie um inteiro não-negativo no campo 'number'." },
        { status: 400 },
      );
    }

    return Response.json({ primes: primesUpTo(number) });
  }),
};

/* Invocar localmente:

  curl -i --location --request POST 'http://127.0.0.1:54321/functions/v1/primes' \
    --header 'apiKey: <SUA_PUBLISHABLE_KEY>' \
    --header 'Content-Type: application/json' \
    --data '{"number": 10}'

  Resposta esperada: { "primes": [2, 3, 5, 7] }
*/
