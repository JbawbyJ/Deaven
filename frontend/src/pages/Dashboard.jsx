import { Flame, Gauge, TrendingUp, Zap } from 'lucide-react';
import DealCard from '../components/DealCard';
import ScoutRunBar from '../components/ScoutRunBar';
import StatCard from '../components/StatCard';
import { formatMargin, formatScore } from '../lib/formatters';
import { useDeals } from '../hooks/useDeals';
import { useStats } from '../hooks/useStats';
import { useDealStore } from '../store/dealStore';

const TIERS = [
  { id: 'all', label: 'All' },
  { id: 'fire', label: 'Fire' },
  { id: 'strong', label: 'Strong' },
  { id: 'watchlist', label: 'Watch' },
  { id: 'pass', label: 'Pass' },
];

export default function Dashboard() {
  const activeTier = useDealStore((s) => s.activeTier);
  const setActiveTier = useDealStore((s) => s.setActiveTier);

  const { data: stats = {} } = useStats();
  const { data: deals = [], isLoading, isError } = useDeals(activeTier);

  const todayCount = stats.total_ingested ?? deals.length ?? 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 lg:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Deal Feed</h1>
          <p className="text-sm text-zinc-500">
            Live pipeline · refreshes every 30s
          </p>
        </div>
        <ScoutRunBar />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Today's Deals"
          value={todayCount}
          sub="Active in feed"
        />
        <StatCard
          label="Fire Deals"
          value={stats.fire_deals ?? 0}
          sub={<Flame className="inline h-3 w-3 text-deaven-fire" />}
        />
        <StatCard
          label="Avg Score"
          value={formatScore(stats.avg_score)}
          sub={<Gauge className="inline h-3 w-3" />}
        />
        <StatCard
          label="Avg Margin"
          value={
            stats.avg_margin != null && stats.avg_margin !== 0
              ? formatMargin(
                  stats.avg_margin <= 1 ? stats.avg_margin : stats.avg_margin / 100,
                )
              : '—'
          }
          sub={<TrendingUp className="inline h-3 w-3" />}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {TIERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTier(id)}
            className={[
              'rounded-full border px-4 py-1.5 text-sm font-medium transition-all',
              activeTier === id
                ? 'border-deaven-gold/50 bg-deaven-gold/10 text-deaven-gold'
                : 'border-deaven-border text-zinc-400 hover:border-zinc-600 hover:text-zinc-200',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="panel flex items-center justify-center gap-2 py-16 text-zinc-500">
          <Zap className="h-4 w-4 animate-pulse text-deaven-gold" />
          Loading deals…
        </div>
      )}

      {isError && (
        <div className="panel py-16 text-center text-sm text-deaven-fire">
          Failed to load deals. Is the API running on port 8000?
        </div>
      )}

      {!isLoading && !isError && deals.length === 0 && (
        <div className="panel flex flex-col items-center justify-center gap-3 py-20 text-center">
          <Zap className="h-8 w-8 text-deaven-gold/50" />
          <h2 className="text-lg font-medium text-zinc-300">No deals yet</h2>
          <p className="max-w-md text-sm text-zinc-500">
            Run scout to score the E46 hunt, or paste a listing URL /{" "}
            <span className="font-mono text-zinc-400">local://bmw-m3-2003</span>{" "}
            in the navbar.
          </p>
        </div>
      )}

      {!isLoading && deals.length > 0 && (
        <div className="space-y-3">
          {deals.map((deal) => (
            <DealCard key={deal.deal_id} deal={deal} />
          ))}
        </div>
      )}
    </div>
  );
}
