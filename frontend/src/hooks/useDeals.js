import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { getDeals } from '../lib/api';
import { useDealStore } from '../store/dealStore';

export function useDeals(tier = 'all') {
  const setDeals = useDealStore((s) => s.setDeals);

  const query = useQuery({
    queryKey: ['deals', tier],
    queryFn: () => getDeals(tier === 'all' ? null : tier),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  useEffect(() => {
    if (query.data) setDeals(query.data);
  }, [query.data, setDeals]);

  return query;
}
