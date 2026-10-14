import api from './api';

export async function searchListings(filters) {
  const params = {};
  Object.entries(filters).forEach(([key, value]) => {
    if (value === '' || value == null) return;
    params[key] = value;
  });
  const { data } = await api.get('/search/listings', { params });
  return data;
}

export async function getSearchPlaces() {
  const { data } = await api.get('/search/places');
  return data;
}

export function searchErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return 'Search failed. Is the API running on port 8000?';
}
