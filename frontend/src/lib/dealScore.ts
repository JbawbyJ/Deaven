/**
 * Fixture stand-in for Builder C PR #12 @ 9cff34b ClusterResult.
 * deal_score = (estimate.mid - asking) / estimate.mid.
 * Positive means the asking price is below the estimate.
 * deal_rating is great | good | fair | high | null.
 * rate_deal's overpriced maps to high. Null is only the unknown case (no estimate).
 */

import type { ClusterResult, DealRating } from '../types/listing';

type FixtureEstimate = {
  low: number;
  mid: number;
  high: number;
  confidence: number;
  comp_count: number;
};

/** Keyed by model. Cars missing from this map have no estimate. */
export const FIXTURE_ESTIMATES: Record<string, FixtureEstimate> = {
  M3: { low: 36000, mid: 40000, high: 46000, confidence: 0.8, comp_count: 4 },
  'RX-7': { low: 31000, mid: 34800, high: 39000, confidence: 0.45, comp_count: 2 },
  S2000: { low: 22000, mid: 24000, high: 25500, confidence: 0.35, comp_count: 1 },
};

const EMPTY_RESULT: ClusterResult = {
  deal_score: null,
  deal_rating: null,
  estimate: { low: null, mid: null, high: null },
  confidence: 0,
  comp_count: 0,
};

export function dealScore(mid: number | null | undefined, asking: number): number | null {
  if (mid == null || !Number.isFinite(mid) || mid <= 0 || !Number.isFinite(asking)) return null;
  return Math.round(((mid - asking) / mid) * 10000) / 10000;
}

/** Mirrors rate_deal thresholds, then maps overpriced onto high. */
export function dealRating(score: number | null): DealRating | null {
  if (score == null) return null;
  if (score >= 0.15) return 'great';
  if (score >= 0.05) return 'good';
  if (score >= -0.05) return 'fair';
  return 'high';
}

export function ratingBadge(rating: DealRating | null | undefined): string | null {
  if (!rating) return null;
  if (rating === 'high') return 'overpriced';
  return rating;
}

export function clusterResult(model: string, asking: number): ClusterResult {
  const spec = FIXTURE_ESTIMATES[model];
  if (!spec) return { ...EMPTY_RESULT, estimate: { low: null, mid: null, high: null } };
  const score = dealScore(spec.mid, asking);
  return {
    deal_score: score,
    deal_rating: dealRating(score),
    estimate: { low: spec.low, mid: spec.mid, high: spec.high },
    confidence: spec.confidence,
    comp_count: spec.comp_count,
  };
}
