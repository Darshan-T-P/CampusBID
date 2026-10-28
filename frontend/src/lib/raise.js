// The minimum raise is worked out by the app, not typed by the seller. This mirrors the server's rule
// (backend/app/services/listings.py default_min_increment) so the Sell page can show it before the listing exists.
// The server is the one that decides; this is only for explaining it.

const TIDY_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000]
const RAISE_FRACTION = 0.05 // about 5% of the starting price

/** The smallest amount a bid must beat the last one by, for an auction starting at `startingPrice`. */
export function defaultMinRaise(startingPrice) {
  const target = startingPrice * RAISE_FRACTION
  let best = TIDY_STEPS[0]
  for (const step of TIDY_STEPS) {
    if (Math.abs(step - target) < Math.abs(best - target)) best = step // strictly closer wins, so a tie keeps the smaller
  }
  return best
}
