import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  ExternalLink,
  Eye,
  Loader2,
  ThumbsDown,
} from 'lucide-react';
import AgentReport from '../components/AgentReport';
import ScoreBadge from '../components/ScoreBadge';
import TierBadge from '../components/TierBadge';
import { getDeal, recordDecision } from '../lib/api';
import {
  formatDaysLeft,
  formatMargin,
  formatMileage,
  formatPrice,
  formatScore,
  formatSource,
} from '../lib/formatters';

const SCORE_DIMENSIONS = [
  { key: 'price_score', label: 'Price', weight: 0.3 },
  { key: 'provenance_score', label: 'Provenance', weight: 0.25 },
  { key: 'demand_score', label: 'Demand', weight: 0.2 },
  { key: 'condition_score', label: 'Condition', weight: 0.15 },
  { key: 'margin_score', label: 'Margin', weight: 0.1 },
];

function ScoreBreakdown({ components }) {
  if (!components) {
    return (
      <p className="text-sm text-zinc-600">Score breakdown pending pipeline completion.</p>
    );
  }

  return (
    <div className="space-y-4">
      {SCORE_DIMENSIONS.map(({ key, label, weight }) => {
        const value = components[key] ?? 0;
        return (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">
                {label}{' '}
                <span className="text-zinc-600">({Math.round(weight * 100)}%)</span>
              </span>
              <span className="font-mono text-deaven-gold">{formatScore(value)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-deaven-bg">
              <div
                className="h-full rounded-full bg-gradient-to-r from-deaven-gold/60 to-deaven-gold animate-barGrow"
                style={{ '--bar-width': `${value}%`, width: `${value}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function DealDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [decisionMsg, setDecisionMsg] = useState(null);

  const { data: deal, isLoading, isError } = useQuery({
    queryKey: ['deal', id],
    queryFn: () => getDeal(id),
    enabled: Boolean(id),
  });

  const decisionMutation = useMutation({
    mutationFn: (decision) => recordDecision(id, decision),
    onSuccess: (_, decision) => {
      setDecisionMsg(`Recorded: ${decision}`);
      queryClient.invalidateQueries({ queryKey: ['deal', id] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-zinc-500">
        <Loader2 className="h-6 w-6 animate-spin text-deaven-gold" />
      </div>
    );
  }

  if (isError || !deal) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-deaven-fire">Deal not found.</p>
        <Link to="/" className="btn-gold mt-4 inline-flex">
          Back to feed
        </Link>
      </div>
    );
  }

  const listing = deal.listing ?? {};
  const ymm = [listing.year, listing.make, listing.model].filter(Boolean).join(' ');
  const images = deal.images?.length ? deal.images : [];
  const daysLeft = formatDaysLeft(listing.end_date);
  const isFire = String(deal.deal_tier ?? '').toLowerCase() === 'fire';

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 lg:px-6">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-zinc-500 transition-colors hover:text-deaven-gold"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to feed
      </Link>

      <div
        className={[
          'panel p-6',
          isFire ? 'shadow-fire border-deaven-fire/30' : '',
        ].join(' ')}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <ScoreBadge score={deal.deal_score} tier={deal.deal_tier} />
              <TierBadge tier={deal.deal_tier} />
              <span className="font-mono text-xs text-zinc-500">
                {formatSource(deal.source)}
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-zinc-100">
              {ymm || listing.title}
            </h1>
            <div className="mt-2 flex flex-wrap gap-4 font-mono text-sm text-zinc-400">
              <span className="text-lg text-deaven-gold">
                {formatPrice(listing.price)}
              </span>
              {listing.mileage != null && (
                <span>{formatMileage(listing.mileage)}</span>
              )}
              {daysLeft && <span>{daysLeft}</span>}
              {deal.valuation_report?.estimated_gross_margin != null && (
                <span className="text-emerald-400">
                  {formatMargin(deal.valuation_report.estimated_gross_margin)} est. margin
                </span>
              )}
            </div>
          </div>

          <a
            href={deal.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-gold shrink-0"
          >
            View listing
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>

      {images.length > 0 && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
          {images.map((src, i) => (
            <div
              key={src + i}
              className="aspect-[4/3] overflow-hidden rounded-lg border border-deaven-border bg-deaven-surface"
            >
              <img
                src={src}
                alt={`${ymm} ${i + 1}`}
                className="h-full w-full object-cover transition-transform hover:scale-105"
              />
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-deaven-gold">
            Score Breakdown
          </h2>
          <ScoreBreakdown components={deal.score_components} />
        </section>

        <section className="panel p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-deaven-gold">
            Narrative
          </h2>
          <p className="text-sm leading-relaxed text-zinc-300">
            {deal.narrative ?? 'Narrative will appear after scoring completes.'}
          </p>
        </section>
      </div>

      <div className="space-y-3">
        <AgentReport title="Vision Report" data={deal.vision_report} />
        <AgentReport title="Risk Report" data={deal.risk_report} />
        <AgentReport title="Valuation Report" data={deal.valuation_report} />
      </div>

      <section className="panel p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-deaven-gold">
          Your Decision
        </h2>
        <div className="flex flex-wrap gap-3">
          {[
            { id: 'acquire', label: 'Acquire', icon: Check, className: 'border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10' },
            { id: 'watchlist', label: 'Watchlist', icon: Eye, className: 'border-deaven-watch/40 text-deaven-watch hover:bg-deaven-watch/10' },
            { id: 'pass', label: 'Pass', icon: ThumbsDown, className: 'border-deaven-pass/40 text-deaven-pass hover:bg-deaven-pass/10' },
          ].map(({ id: decision, label, icon: Icon, className }) => (
            <button
              key={decision}
              type="button"
              disabled={decisionMutation.isPending}
              onClick={() => decisionMutation.mutate(decision)}
              className={[
                'inline-flex items-center gap-2 rounded-md border px-5 py-2.5 text-sm font-medium transition-all',
                className,
              ].join(' ')}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
        {decisionMsg && (
          <p className="mt-3 font-mono text-xs text-zinc-500">{decisionMsg}</p>
        )}
      </section>
    </div>
  );
}
