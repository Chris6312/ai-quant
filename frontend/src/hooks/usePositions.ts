// No /positions list endpoint exists yet in the backend.
// This hook derives what it can from /admin/reconcile and returns
// a typed empty array until the route is added.
// When backend adds GET /positions, swap the fetch call below.

export type Position = {
  id: string;
  symbol: string;
  assetClass: 'stock' | 'crypto';
  side: 'long' | 'short';
  entryPrice: number;
  size: number;
  slPrice: number | null;
  tpPrice: number | null;
  mlConfidence: number | null;
  researchScore: number | null;
  strategyId: string | null;
  status: string;
  openedAt: string;
};

// Empty until backend exposes GET /positions — Dashboard shows count from reconcile instead.
export function usePositions(): { positions: Position[] } {
  return { positions: [] };
}
