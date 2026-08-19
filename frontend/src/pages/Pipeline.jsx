import { useStats } from '../hooks/useStats';
import StatCard from '../components/StatCard';
import { formatMargin, formatScore } from '../lib/formatters';

export default function Pipeline() {
  const { data: stats = {}, isLoading } = useStats();

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 lg:px-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Pipeline</h1>
        <p className="text-sm text-zinc-500">Aggregate scoring pipeline metrics</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-zinc-500">Loading stats…</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label="Total Ingested" value={stats.total_ingested ?? 0} />
          <StatCard label="Fire" value={stats.fire_deals ?? 0} />
          <StatCard label="Strong" value={stats.strong_deals ?? 0} />
          <StatCard label="Watchlist Tier" value={stats.watchlist_deals ?? 0} />
          <StatCard label="Avg Score" value={formatScore(stats.avg_score)} />
          <StatCard label="Avg Margin" value={formatMargin(stats.avg_margin)} />
        </div>
      )}
    </div>
  );
}
