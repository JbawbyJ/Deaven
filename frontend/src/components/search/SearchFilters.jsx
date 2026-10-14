import { useEffect, useState } from 'react';

const RADIUS_OPTIONS = [25, 50, 100, 250, 500, 1000, 2000, 3000];

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-wider text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

export default function SearchFilters({ filters, places, onApply, onClear }) {
  const [draft, setDraft] = useState(filters);

  useEffect(() => {
    setDraft(filters);
  }, [filters]);

  function set(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <form
      className="panel space-y-4 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onApply(draft);
      }}
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Location">
          <input
            className="input-dark"
            list="deaven-places"
            value={draft.location}
            placeholder="City, or lat,lng"
            onChange={(event) => set('location', event.target.value)}
          />
          <datalist id="deaven-places">
            {(places ?? []).map((place) => (
              <option key={place.label} value={place.label} />
            ))}
          </datalist>
        </Field>
        <Field label="Radius">
          <select
            className="input-dark"
            value={draft.radius_miles}
            onChange={(event) => set('radius_miles', event.target.value)}
          >
            {RADIUS_OPTIONS.map((miles) => (
              <option key={miles} value={miles}>
                {miles} mi
              </option>
            ))}
          </select>
        </Field>
        <Field label="Make">
          <input
            className="input-dark"
            value={draft.make}
            onChange={(event) => set('make', event.target.value)}
          />
        </Field>
        <Field label="Model">
          <input
            className="input-dark"
            value={draft.model}
            onChange={(event) => set('model', event.target.value)}
          />
        </Field>
        <Field label="Year from">
          <input
            className="input-dark"
            inputMode="numeric"
            value={draft.year_min}
            onChange={(event) => set('year_min', event.target.value)}
          />
        </Field>
        <Field label="Year to">
          <input
            className="input-dark"
            inputMode="numeric"
            value={draft.year_max}
            onChange={(event) => set('year_max', event.target.value)}
          />
        </Field>
        <Field label="Min price">
          <input
            className="input-dark"
            inputMode="numeric"
            value={draft.price_min}
            onChange={(event) => set('price_min', event.target.value)}
          />
        </Field>
        <Field label="Max price">
          <input
            className="input-dark"
            inputMode="numeric"
            value={draft.price_max}
            onChange={(event) => set('price_max', event.target.value)}
          />
        </Field>
        <Field label="Max mileage">
          <input
            className="input-dark"
            inputMode="numeric"
            value={draft.mileage_max}
            onChange={(event) => set('mileage_max', event.target.value)}
          />
        </Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn-gold">
          Search area
        </button>
        <button type="button" className="btn-gold border-zinc-700 text-zinc-300" onClick={onClear}>
          Clear filters
        </button>
      </div>
    </form>
  );
}
