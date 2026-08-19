import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { getStats } from '../lib/api';
import { useDealStore } from '../store/dealStore';

export function useStats() {
  const setStats = useDealStore((s) => s.setStats);

  const query = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (query.data) setStats(query.data);
  }, [query.data, setStats]);

  return query;
}
