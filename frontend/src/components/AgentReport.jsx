import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

function renderValue(value, depth = 0) {
  if (value == null) return <span className="text-zinc-600">—</span>;
  if (typeof value !== 'object') {
    return <span className="font-mono text-sm text-zinc-300">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-zinc-600">[]</span>;
    return (
      <ul className="mt-1 space-y-1">
        {value.map((item, i) => (
          <li key={i} className="text-sm text-zinc-400">
            {typeof item === 'object' ? JSON.stringify(item) : String(item)}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <dl className={depth > 0 ? 'ml-3 border-l border-deaven-border pl-3' : ''}>
      {Object.entries(value).map(([key, val]) => (
        <div key={key} className="grid grid-cols-[140px_1fr] gap-2 py-1">
          <dt className="font-mono text-xs uppercase tracking-wide text-zinc-500">
            {key.replace(/_/g, ' ')}
          </dt>
          <dd>{renderValue(val, depth + 1)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function AgentReport({ title, data }) {
  const [open, setOpen] = useState(true);
  const hasData = data && Object.keys(data).length > 0;

  return (
    <section className="panel overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-zinc-900/50"
      >
        <span className="text-sm font-semibold uppercase tracking-wider text-deaven-gold">
          {title}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-zinc-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-zinc-500" />
        )}
      </button>
      {open && (
        <div className="border-t border-deaven-border px-4 py-3">
          {hasData ? renderValue(data) : (
            <p className="text-sm text-zinc-600">Report pending…</p>
          )}
        </div>
      )}
    </section>
  );
}
