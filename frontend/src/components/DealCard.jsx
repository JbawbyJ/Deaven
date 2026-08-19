import { useNavigate } from 'react-router-dom';
import { Clock, TrendingUp } from 'lucide-react';
import ScoreBadge from './ScoreBadge';
import {
  formatDaysLeft,
  formatMargin,
  formatMileage,
  formatPrice,
  formatSource,
} from '../lib/formatters';

export default function DealCard({ deal }) {
  const navigate = useNavigate();
  const isFire = String(deal.deal_tier ?? '').toLowerCase() === 'fire';

  const ymm = [deal.year, deal.make, deal.model].filter(Boolean).join(' ') || deal.title;
  const margin =
    deal.estimated_margin ??
    deal.valuation_report?.estimated_gross_margin ??
    null;
  const mileage = deal.mileage ?? deal.listing?.mileage;
  const endDate = deal.end_date ?? deal.listing?.end_date;
  const daysLeft = formatDaysLeft(endDate);
  const narrative = deal.narrative ?? '';

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/deals/${deal.deal_id}`)}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/deals/${deal.deal_id}`)}
      className={[
        'group panel cursor-pointer p-4 transition-all duration-200',
        'hover:border-deaven-gold/30 hover:bg-zinc-900/50',
        isFire ? 'shadow-fire border-deaven-fire/30' : '',
      ].join(' ')}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <ScoreBadge score={deal.deal_score} tier={deal.deal_tier} />
            <span className="rounded border border-deaven-border bg-deaven-bg px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
              {formatSource(deal.source)}
            </span>
          </div>

          <h3 className="truncate text-base font-semibold text-zinc-100 group-hover:text-deaven-gold">
            {ymm}
          </h3>

          {narrative && (
            <p className="line-clamp-2 text-sm leading-relaxed text-zinc-500">
              {narrative}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
          <span className="font-mono text-lg font-semibold text-deaven-gold">
            {formatPrice(deal.price ?? deal.listing?.price)}
          </span>
          {margin != null && (
            <span className="flex items-center gap-1 font-mono text-xs text-emerald-400">
              <TrendingUp className="h-3 w-3" />
              {formatMargin(margin)} margin
            </span>
          )}
          {mileage != null && (
            <span className="font-mono text-xs text-zinc-500">
              {formatMileage(mileage)}
            </span>
          )}
          {daysLeft && (
            <span className="flex items-center gap-1 font-mono text-xs text-zinc-400">
              <Clock className="h-3 w-3" />
              {daysLeft}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
