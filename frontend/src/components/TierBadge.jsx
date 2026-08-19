import { formatTier, tierBgClass, tierColorClass } from '../lib/formatters';

export default function TierBadge({ tier }) {
  return (
    <span
      className={[
        'inline-flex rounded border px-2 py-0.5 font-mono text-[10px] font-bold tracking-wider',
        tierBgClass(tier),
        tierColorClass(tier),
      ].join(' ')}
    >
      {formatTier(tier)}
    </span>
  );
}
