import type { SearchQuery, SearchSort } from '../../types/listing';

type Props = {
  draft: SearchQuery;
  onChange: (next: SearchQuery) => void;
  onApply: () => void;
};

const FIELDS: { key: keyof SearchQuery; label: string; inputMode?: 'numeric' | 'decimal' }[] = [
  { key: 'make', label: 'Make' },
  { key: 'model', label: 'Model' },
  { key: 'year_min', label: 'Year from', inputMode: 'numeric' },
  { key: 'year_max', label: 'Year to', inputMode: 'numeric' },
  { key: 'price_min', label: 'Price min', inputMode: 'decimal' },
  { key: 'price_max', label: 'Price max', inputMode: 'decimal' },
  { key: 'mileage_max', label: 'Max mileage', inputMode: 'numeric' },
  { key: 'location', label: 'Location' },
  { key: 'radius', label: 'Radius', inputMode: 'decimal' },
];

export default function SearchFilters({ draft, onChange, onApply }: Props) {
  function update(key: keyof SearchQuery, value: string) {
    onChange({ ...draft, [key]: value });
  }

  return (
    <form
      className="panel grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3"
      onSubmit={(event) => {
        event.preventDefault();
        onApply();
      }}
    >
      {FIELDS.map(({ key, label, inputMode }) => (
        <label key={key} className="flex flex-col gap-1 text-xs text-zinc-500">
          {label}
          <input
            className="input-dark"
            inputMode={inputMode}
            value={draft[key]}
            placeholder={key === 'location' ? 'Austin, TX' : key === 'radius' ? 'miles' : ''}
            onChange={(event) => update(key, event.target.value)}
          />
        </label>
      ))}
      <label className="flex flex-col gap-1 text-xs text-zinc-500">
        Sort
        <select
          className="input-dark"
          value={draft.sort}
          onChange={(event) => update('sort', event.target.value as SearchSort)}
        >
          <option value="price">Price</option>
          <option value="deal">Deal</option>
          <option value="distance">Distance</option>
        </select>
      </label>
      <div className="flex items-end">
        <button type="submit" className="btn-gold">
          Apply
        </button>
      </div>
    </form>
  );
}
