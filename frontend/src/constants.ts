// Mirrors backend app/candle/kraken_worker.py KRAKEN_UNIVERSE
// These pairs always have active candle workers — no dynamic changes.
export const KRAKEN_UNIVERSE: readonly string[] = [
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD',
  'AVAX/USD', 'DOT/USD', 'LINK/USD', 'MATIC/USD', 'LTC/USD',
  'UNI/USD', 'ATOM/USD', 'NEAR/USD', 'ALGO/USD', 'FIL/USD',
] as const;
