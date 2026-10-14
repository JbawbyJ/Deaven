import { describe, expect, it } from 'vitest';
import { dealRating, ratingBadge } from './dealScore';

describe('deal rating', () => {
  it('maps overpriced onto high and keeps null for an unknown score', () => {
    expect(dealRating(0.2)).toBe('great');
    expect(dealRating(0.05)).toBe('good');
    expect(dealRating(0)).toBe('fair');
    expect(dealRating(-0.1)).toBe('high');
    expect(dealRating(-0.2)).toBe('high');
    expect(dealRating(null)).toBeNull();
  });

  it('renders high as an overpriced badge', () => {
    expect(ratingBadge('high')).toBe('overpriced');
    expect(ratingBadge('great')).toBe('great');
    expect(ratingBadge(null)).toBeNull();
  });
});
