import { useState } from 'react';
import { Loader2, Scale } from 'lucide-react';
import ComparisonTable from '../components/compare/ComparisonTable';
import { compareListings } from '../lib/api';
import { formatPrice } from '../lib/formatters';
import { useDeals } from '../hooks/useDeals';

const MIN_LISTINGS = 2;
const MAX_LISTINGS = 4;

function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  return 'Compare failed. Is the API running on port 8000?';
}

export default function Compare() {
  const { data: deals = [], isLoading, isError } = useDeals('all');
  const [selected, setSelected] = useState([]);
  const [rows, setRows] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState(null);

  const atMax = selected.length >= MAX_LISTINGS;

  function toggle(id) {
    setRows(null);
    setError(null);
    setSelected((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= MAX_LISTINGS) return current;
      return [...current, id];
    });
  }

  async function handleCompare() {
    if (selected.length < MIN_LISTINGS) return;
    setComparing(true);
    setError(null);
    try {
      setRows(await compareListings(selected));
    } catch (err) {
      setRows(null);
      setError(errorMessage(err));
    } finally {
      setComparing(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 lg:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Compare</h1>
          <p className="text-sm text-zinc-500">
            Select {MIN_LISTINGS} to {MAX_LISTINGS} listings. One row is marked best value.
          </p>
        </div>
        <button
          type="button"
          onClick={handleCompare}
          disabled={selected.length < MIN_LISTINGS || comparing}
          className="btn-gold disabled:cursor-not-allowed disabled:opacity-40"
        >
          {comparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scale className="h-4 w-4" />}
          {selected.length >= MIN_LISTINGS ? `Compare ${selected.length}` : 'Compare'}
        </button>
      </div>

      {isLoading && (
        <div className="panel flex items-center justify-center gap-2 py-16 text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin text-deaven-gold" />
          Loading listings…
        </div>
      )}

      {isError && (
        <div className="panel py-16 text-center text-sm text-deaven-fire">
          Failed to load listings. Is the API running on port 8000?
        </div>
      )}

      {!isLoading && !isError && deals.length === 0 && (
        <div className="panel py-16 text-center text-sm text-zinc-500">
          No listings yet. Run scout or paste a listing URL in the navbar.
        </div>
      )}

      {!isLoading && deals.length > 0 && (
        <ul className="space-y-2">
          {deals.map((deal) => {
            const id = deal.deal_id;
            const checked = selected.includes(id);
            const disabled = !checked && atMax;
            const name = [deal.year, deal.make, deal.model].filter(Boolean).join(' ') || deal.title;
            return (
              <li key={id}>
                <label
                  className={[
                    'panel flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors',
                    checked ? 'border-deaven-gold/40 bg-deaven-gold/5' : 'hover:border-zinc-700',
                    disabled ? 'cursor-not-allowed opacity-50' : '',
                  ].join(' ')}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-deaven-gold"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => toggle(id)}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{name}</span>
                  <span className="font-mono text-sm text-deaven-gold">{formatPrice(deal.price)}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-deaven-fire">{error}</div>
      )}

      {rows && (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500">
            Best value is the strongest deal rating, then the lowest asking price. Confidence
            stays insufficient, and the rating stays unknown, when the set has no comps.
          </p>
          <ComparisonTable rows={rows} />
        </div>
      )}
    </div>
  );
}
