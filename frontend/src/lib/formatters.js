const TIER_LABELS = {
  fire: 'FIRE',
  strong: 'STRONG',
  watchlist: 'WATCH',
  pass: 'PASS',
  discard: 'DISCARD',
};

export function formatPrice(n) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatScore(n) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return String(Math.round(Number(n)));
}

export function formatTier(t) {
  if (!t) return '—';
  return TIER_LABELS[String(t).toLowerCase()] ?? String(t).toUpperCase();
}

export function formatMileage(n) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  const miles = Number(n);
  if (miles >= 1000) return `${Math.round(miles / 1000)}k mi`;
  return `${miles} mi`;
}

export function formatDaysLeft(date) {
  if (!date) return null;
  const end = new Date(date);
  if (Number.isNaN(end.getTime())) return null;
  const diffMs = end.getTime() - Date.now();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0) return 'Ended';
  if (days === 0) return 'Today';
  return `${days}d left`;
}

export function formatMargin(decimal) {
  if (decimal == null || Number.isNaN(Number(decimal))) return '—';
  return `${(Number(decimal) * 100).toFixed(1)}%`;
}

export function formatSource(source) {
  if (!source) return '—';
  const map = {
    bat: 'Bring a Trailer',
    cab: 'Cars & Bids',
    ebay: 'eBay',
    facebook: 'Facebook',
    autotrader: 'AutoTrader',
    hemmings: 'Hemmings',
    craigslist: 'Craigslist',
    manual: 'Manual',
  };
  return map[String(source).toLowerCase()] ?? source;
}

export function tierColorClass(tier) {
  const t = String(tier ?? '').toLowerCase();
  if (t === 'fire') return 'text-deaven-fire';
  if (t === 'strong') return 'text-deaven-strong';
  if (t === 'watchlist') return 'text-deaven-watch';
  return 'text-deaven-pass';
}

export function tierBgClass(tier) {
  const t = String(tier ?? '').toLowerCase();
  if (t === 'fire') return 'bg-deaven-fire/15 border-deaven-fire/40';
  if (t === 'strong') return 'bg-deaven-strong/15 border-deaven-strong/40';
  if (t === 'watchlist') return 'bg-deaven-watch/15 border-deaven-watch/40';
  return 'bg-deaven-pass/15 border-deaven-pass/40';
}
