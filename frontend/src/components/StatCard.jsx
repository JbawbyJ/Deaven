export default function StatCard({ label, value, sub }) {
  return (
    <div className="panel flex flex-col gap-1 p-4">
      <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <span className="font-mono text-2xl font-semibold text-deaven-gold">
        {value}
      </span>
      {sub && <span className="text-xs text-zinc-600">{sub}</span>}
    </div>
  );
}
