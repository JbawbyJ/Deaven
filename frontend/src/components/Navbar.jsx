import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Loader2, Radar, Search } from 'lucide-react';
import { ingestURL } from '../lib/api';

const NAV = [
  { to: '/', label: 'Feed' },
  { to: '/watchlist', label: 'Watchlist' },
  { to: '/pipeline', label: 'Pipeline' },
];

export default function Navbar() {
  const location = useLocation();
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  async function handleIngest(e) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const deal = await ingestURL(url.trim());
      setMessage(`Ingested ${deal.deal_id.slice(0, 8)}…`);
      setUrl('');
    } catch (err) {
      setMessage(err.response?.data?.detail ?? 'Ingest failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <header className="sticky top-0 z-50 border-b border-deaven-border bg-deaven-bg/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2">
            <Radar className="h-5 w-5 text-deaven-gold" />
            <span className="font-mono text-lg font-bold tracking-[0.2em] text-deaven-gold">
              DEAVEN
            </span>
          </Link>

          <nav className="flex items-center gap-1">
            {NAV.map(({ to, label }) => {
              const active =
                to === '/'
                  ? location.pathname === '/'
                  : location.pathname.startsWith(to);
              return (
                <Link
                  key={to}
                  to={to}
                  className={[
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    active
                      ? 'bg-deaven-gold/10 text-deaven-gold'
                      : 'text-zinc-400 hover:text-zinc-100',
                  ].join(' ')}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>

        <form
          onSubmit={handleIngest}
          className="flex w-full max-w-xl items-center gap-2 lg:w-auto"
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste listing URL to ingest…"
              className="input-dark pl-9"
            />
          </div>
          <button type="submit" disabled={loading} className="btn-gold shrink-0">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Submit'}
          </button>
        </form>
      </div>
      {message && (
        <div className="border-t border-deaven-border px-6 py-1.5 font-mono text-xs text-zinc-500">
          {message}
        </div>
      )}
    </header>
  );
}
