import { formatScore, formatTier, tierBgClass } from '../lib/formatters';

export default function ScoreBadge({ score, tier }) {
  const t = String(tier ?? '').toLowerCase();
  const isFire = t === 'fire';

  return (
    <div
      className={[
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-xs font-semibold',
        tierBgClass(tier),
        isFire ? 'animate-pulseFire' : '',
      ].join(' ')}
    >
      <span>{formatScore(score)}</span>
      <span className="opacity-70">·</span>
      <span>{formatTier(tier)}</span>
    </div>
  );
}
