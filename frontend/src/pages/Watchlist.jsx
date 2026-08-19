import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Radar } from 'lucide-react';
import { createWatchlist, getWatchlists } from '../lib/api';

function parseList(value) {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

const EMPTY_FORM = {
  name: '',
  makes: '',
  models: '',
  year_min: '',
  year_max: '',
  price_min: '',
  price_max: '',
};

export default function Watchlist() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);

  const { data: watchlists = [], isLoading } = useQuery({
    queryKey: ['watchlists'],
    queryFn: getWatchlists,
  });

  const createMutation = useMutation({
    mutationFn: createWatchlist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlists'] });
      setForm(EMPTY_FORM);
    },
  });

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    createMutation.mutate({
      name: form.name,
      makes: parseList(form.makes),
      models: parseList(form.models),
      year_min: form.year_min ? Number(form.year_min) : null,
      year_max: form.year_max ? Number(form.year_max) : null,
      price_min: form.price_min ? Number(form.price_min) : null,
      price_max: form.price_max ? Number(form.price_max) : null,
      sources: [],
      active: true,
    });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 lg:px-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Watchlists</h1>
        <p className="text-sm text-zinc-500">
          Saved search rules for the scout pipeline
        </p>
      </div>

      <div className="space-y-3">
        {isLoading && (
          <p className="text-sm text-zinc-500">Loading watchlists…</p>
        )}
        {!isLoading && watchlists.length === 0 && (
          <div className="panel flex flex-col items-center gap-2 py-12 text-center">
            <Radar className="h-8 w-8 text-deaven-gold/40" />
            <p className="text-sm text-zinc-500">No watchlists configured yet.</p>
          </div>
        )}
        {watchlists.map((wl) => (
          <article key={wl.filter_id} className="panel p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-medium text-zinc-100">{wl.name}</h2>
                <div className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-zinc-500">
                  {wl.makes?.length > 0 && (
                    <span>Makes: {wl.makes.join(', ')}</span>
                  )}
                  {wl.models?.length > 0 && (
                    <span>Models: {wl.models.join(', ')}</span>
                  )}
                  {(wl.year_min || wl.year_max) && (
                    <span>
                      Years: {wl.year_min ?? '—'}–{wl.year_max ?? '—'}
                    </span>
                  )}
                  {(wl.price_min || wl.price_max) && (
                    <span>
                      Price: ${wl.price_min ?? 0}–${wl.price_max ?? '∞'}
                    </span>
                  )}
                </div>
              </div>
              <span
                className={[
                  'rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase',
                  wl.active
                    ? 'border-emerald-500/30 text-emerald-400'
                    : 'border-zinc-700 text-zinc-600',
                ].join(' ')}
              >
                {wl.active ? 'Active' : 'Paused'}
              </span>
            </div>
          </article>
        ))}
      </div>

      <section className="panel p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-deaven-gold">
          <Plus className="h-4 w-4" />
          New Watchlist
        </h2>
        <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
          <label className="sm:col-span-2">
            <span className="mb-1 block text-xs text-zinc-500">Name</span>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              required
              className="input-dark"
              placeholder="E46 M3 Hunt"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Makes (comma-separated)</span>
            <input
              name="makes"
              value={form.makes}
              onChange={handleChange}
              className="input-dark"
              placeholder="BMW, Porsche"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Models (comma-separated)</span>
            <input
              name="models"
              value={form.models}
              onChange={handleChange}
              className="input-dark"
              placeholder="M3, 911"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Year min</span>
            <input
              name="year_min"
              type="number"
              value={form.year_min}
              onChange={handleChange}
              className="input-dark"
              placeholder="2001"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Year max</span>
            <input
              name="year_max"
              type="number"
              value={form.year_max}
              onChange={handleChange}
              className="input-dark"
              placeholder="2006"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Price min ($)</span>
            <input
              name="price_min"
              type="number"
              value={form.price_min}
              onChange={handleChange}
              className="input-dark"
              placeholder="15000"
            />
          </label>
          <label>
            <span className="mb-1 block text-xs text-zinc-500">Price max ($)</span>
            <input
              name="price_max"
              type="number"
              value={form.price_max}
              onChange={handleChange}
              className="input-dark"
              placeholder="60000"
            />
          </label>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn-gold"
            >
              {createMutation.isPending ? 'Creating…' : 'Create Watchlist'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
