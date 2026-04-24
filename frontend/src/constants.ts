// Mirrors backend canonical crypto scope.
// Phase 1 semantics: crypto universe === crypto watchlist. Runtime workers and
// prediction coverage are downstream concerns and are not implied by this list alone.
export const KRAKEN_UNIVERSE: readonly string[] = [
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'LTC/USD', 'BCH/USD',
  'LINK/USD', 'UNI/USD', 'AVAX/USD', 'DOGE/USD', 'DOT/USD',
  'AAVE/USD', 'CRV/USD', 'SUSHI/USD', 'SHIB/USD', 'XTZ/USD',
] as const;
