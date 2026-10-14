import { formatMileage, formatPrice } from '../../lib/formatters';
import type { ListingGroup } from '../../lib/groupListings';

type Props = {
  groups: ListingGroup[];
  selectedKey: string | null;
  onSelect: (vehicleKey: string) => void;
};

export default function ResultsList({ groups, selectedKey, onSelect }: Props) {
  if (!groups.length) {
    return (
      <div className="panel py-16 text-center text-sm text-zinc-500">
        No listings match these filters.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {groups.map((group) => {
        const selected = group.cluster.vehicle_key === selectedKey;
        return (
          <article
            key={group.cluster.vehicle_key}
            aria-label={group.title}
            aria-current={selected ? 'true' : undefined}
            tabIndex={0}
            onClick={() => onSelect(group.cluster.vehicle_key)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSelect(group.cluster.vehicle_key);
            }}
            className={[
              'panel cursor-pointer p-4 transition-colors',
              selected ? 'border-deaven-gold/50' : 'hover:border-deaven-gold/30',
            ].join(' ')}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-zinc-100">{group.title}</h2>
                <p className="mt-1 text-xs text-zinc-500">
                  {group.cluster.match_method === 'vin' ? 'Same VIN' : 'Fuzzy vehicle key'}
                  {group.mileage != null ? ` · ${formatMileage(group.mileage)}` : ''}
                  {group.location?.label ? ` · ${group.location.label}` : ''}
                </p>
              </div>
              <span className="font-mono text-sm text-deaven-gold">
                {formatPrice(group.minPrice)}
              </span>
            </div>
            <ul className="mt-3 space-y-1">
              {group.offers.map((offer) => (
                <li key={offer.observationId} className="flex flex-wrap items-baseline gap-x-3 text-sm">
                  <a
                    href={offer.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-zinc-300 underline-offset-2 hover:text-deaven-gold hover:underline"
                    onClick={(event) => event.stopPropagation()}
                  >
                    {offer.sourceName}
                  </a>
                  <span className="font-mono text-zinc-100">{formatPrice(offer.price)}</span>
                  {offer.previousAsking != null && (
                    <span className="text-xs text-emerald-400">
                      {`down from ${formatPrice(offer.previousAsking)}`}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {group.observations.some((item) => item.vin_note === 'invalid') && (
              <p className="mt-2 text-xs text-zinc-500">Invalid VIN, grouped by the fuzzy vehicle key.</p>
            )}
            {group.observations.some((item) => item.vin_note === 'missing') && (
              <p className="mt-2 text-xs text-zinc-500">No VIN, grouped by the fuzzy vehicle key.</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
