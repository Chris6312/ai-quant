// Mirrors backend canonical crypto scope.
// Phase 1 semantics: crypto universe === crypto watchlist. Runtime workers and
// prediction coverage are downstream concerns and are not implied by this list alone.
export const KRAKEN_UNIVERSE: readonly string[] = [
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD',
  'AVAX/USD', 'DOT/USD', 'LINK/USD', 'MATIC/USD', 'LTC/USD',
  'UNI/USD', 'ATOM/USD', 'NEAR/USD', 'ALGO/USD', 'FIL/USD',
] as const;
