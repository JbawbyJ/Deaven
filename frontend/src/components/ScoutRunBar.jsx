import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Radar } from 'lucide-react';
import { getHealth, runScout } from '../lib/api';

function formatScout(last) {
  if (!last?.at) return 'No scout run yet';
  const when = new Date(last.at).toLocaleString();
  const fire = last.tiers?.fire ?? last.tiers?.FIRE ?? 0;
  return `${when} · ${last.new_listings ?? 0} listings · Fire ${fire}`;
}

export default function ScoutRunBar() {
  const queryClient = useQueryClient();
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
  });

  const mutation = useMutation({
    mutationFn: () => runScout(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deals'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['health'] });
    },
  });

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        className="btn-gold"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Radar className="h-4 w-4" />
        )}
        Run scout
      </button>
      <p className="font-mono text-xs text-zinc-500">
        {mutation.isError
          ? mutation.error?.response?.data?.detail || 'Scout failed'
          : formatScout(health?.last_scout)}
      </p>
    </div>
  );
}
