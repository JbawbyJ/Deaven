import { Link } from 'react-router-dom';
import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { formatDeltaPct, formatMileage, formatPrice, formatTrend } from '../../lib/formatters';

const RATING_CLASS = {
  great: 'border-emerald-400/40 bg-emerald-400/15 text-emerald-300',
  good: 'border-emerald-600/40 bg-emerald-600/10 text-emerald-400',
  fair: 'border-deaven-gold/40 bg-deaven-gold/10 text-deaven-gold',
  high: 'border-deaven-strong/40 bg-deaven-strong/15 text-deaven-strong',
  overpriced: 'border-deaven-fire/40 bg-deaven-fire/15 text-deaven-fire',
  unknown: 'border-deaven-border bg-deaven-bg text-zinc-300',
};

function vehicleName(row) {
  const name = [row.year, row.make, row.model].filter(Boolean).join(' ');
  return name || row.listing_id;
}

function DealRatingBadge({ rating }) {
  const key = String(rating ?? 'unknown').toLowerCase();
  const label = key === 'great' || key === 'good' || key === 'fair' || key === 'high' || key === 'overpriced' || key === 'unknown'
    ? key
    : String(rating);
  return (
    <span
      className={[
        'inline-flex rounded-full border px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-wide',
        RATING_CLASS[key] ?? RATING_CLASS.unknown,
      ].join(' ')}
    >
      {label}
    </span>
  );
}

function TrendCell({ history }) {
  if (!history) {
    return <span className="text-zinc-300">no history</span>;
  }
  const trend = formatTrend(history.trend) ?? 'unknown';
  const Icon = trend === 'down' ? TrendingDown : trend === 'up' ? TrendingUp : trend === 'flat' ? Minus : null;
  const color =
    trend === 'down' ? 'text-emerald-400' : trend === 'up' ? 'text-deaven-fire' : 'text-zinc-300';
  return (
    <span className={['inline-flex items-center gap-1 font-mono text-sm', color].join(' ')}>
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {trend}
    </span>
  );
}

function deltaClass(fraction) {
  if (fraction == null || Number(fraction) === 0) return 'text-zinc-300';
  return Number(fraction) < 0 ? 'text-emerald-400' : 'text-deaven-fire';
}

export default function ComparisonTable({ rows }) {
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-zinc-500">
              Listing
            </th>
            {rows.map((row) => (
              <th
                key={row.listing_id}
                className={[
                  'min-w-[160px] px-4 py-3 text-left align-bottom',
                  row.best_value ? 'bg-deaven-gold/10' : '',
                ].join(' ')}
              >
                {row.best_value && (
                  <span className="mb-2 inline-flex rounded border border-deaven-gold/50 bg-deaven-gold/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-deaven-gold">
                    Best value
                  </span>
                )}
                <Link
                  to={`/deals/${row.listing_id}`}
                  className="block text-sm font-semibold text-zinc-100 hover:text-deaven-gold"
                >
                  {vehicleName(row)}
                </Link>
                <span className="mt-0.5 block font-mono text-xs font-normal text-zinc-500">
                  {row.trim || '—'}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Asking price
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={[
                  'px-4 py-3 font-mono text-base font-semibold text-deaven-gold',
                  row.best_value ? 'bg-deaven-gold/10' : '',
                ].join(' ')}
              >
                {formatPrice(row.asking_price)}
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Estimate
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3 font-mono text-zinc-100', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                {formatPrice(row.estimate)}
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Confidence
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3 font-mono text-sm text-zinc-300', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                {row.confidence || 'insufficient'}
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Vs estimate
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={[
                  'px-4 py-3 font-mono text-sm',
                  deltaClass(row.delta_vs_estimate_pct),
                  row.best_value ? 'bg-deaven-gold/10' : '',
                ].join(' ')}
              >
                {formatDeltaPct(row.delta_vs_estimate_pct)}
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Deal rating
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                <DealRatingBadge rating={row.deal_rating} />
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Price trend
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                <TrendCell history={row.price_history} />
              </td>
            ))}
          </tr>
          <tr className="border-b border-deaven-border">
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Mileage
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3 font-mono text-zinc-300', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                {formatMileage(row.mileage)}
              </td>
            ))}
          </tr>
          <tr>
            <th className="sticky left-0 z-10 bg-deaven-surface px-4 py-3 text-left text-xs font-medium text-zinc-500">
              Region
            </th>
            {rows.map((row) => (
              <td
                key={row.listing_id}
                className={['px-4 py-3 font-mono text-zinc-300', row.best_value ? 'bg-deaven-gold/10' : ''].join(' ')}
              >
                {row.region || '—'}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
