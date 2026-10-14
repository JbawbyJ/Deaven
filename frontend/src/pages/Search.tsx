import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ListingMap from '../components/search/ListingMap';
import ResultsList from '../components/search/ResultsList';
import SearchFilters from '../components/search/SearchFilters';
import { groupListings, sortGroups } from '../lib/groupListings';
import { searchListings } from '../lib/searchClient';
import { queryFromSearchParams, searchParamsFromQuery } from '../lib/searchParams';
import type { SearchQuery } from '../types/listing';

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const paramKey = searchParams.toString();
  const query = useMemo(() => queryFromSearchParams(searchParams), [searchParams, paramKey]);
  const [draft, setDraft] = useState<SearchQuery>(query);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    setDraft(query);
  }, [paramKey, query]);

  const result = useQuery({
    queryKey: ['listings-search', paramKey],
    queryFn: () => searchListings(query),
  });

  const groups = useMemo(
    () => sortGroups(groupListings(result.data?.listings ?? []), query.sort),
    [result.data, query.sort],
  );

  useEffect(() => {
    if (selectedKey && !groups.some((group) => group.cluster.vehicle_key === selectedKey)) {
      setSelectedKey(null);
    }
  }, [groups, selectedKey]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 lg:px-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Search</h1>
        <p className="text-sm text-zinc-500">
          One car across sources, plotted from ListingLocation latitude and longitude.
        </p>
      </div>

      <SearchFilters
        draft={draft}
        onChange={setDraft}
        onApply={() => setSearchParams(searchParamsFromQuery(draft))}
      />

      {query.sort === 'deal' && (
        <p className="text-sm text-zinc-400">
          Deal score is not on the listing model, so results follow price.
        </p>
      )}

      {result.data?.note && (
        <p className="text-xs leading-relaxed text-zinc-500">{result.data.note}</p>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-2">
        {result.isLoading ? (
          <div className="panel py-16 text-center text-sm text-zinc-500">Searching…</div>
        ) : (
          <ResultsList groups={groups} selectedKey={selectedKey} onSelect={setSelectedKey} />
        )}
        <ListingMap groups={groups} selectedKey={selectedKey} onSelect={setSelectedKey} />
      </div>
    </div>
  );
}
