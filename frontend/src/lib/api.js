import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

export async function getDeals(tier, limit = 50) {
  const params = { limit };
  if (tier && tier !== 'all') params.tier = tier;
  const { data } = await api.get('/deals', { params });
  return data;
}

export async function getDeal(id) {
  const { data } = await api.get(`/deals/${id}`);
  return data;
}

export async function ingestURL(url) {
  const { data } = await api.post('/deals/ingest', { url });
  return data;
}

export async function getStats() {
  const { data } = await api.get('/stats/pipeline');
  return data;
}

export async function getWatchlists() {
  const { data } = await api.get('/watchlists');
  return data;
}

export async function createWatchlist(payload) {
  const { data } = await api.post('/watchlists', payload);
  return data;
}

export async function recordDecision(id, decision) {
  const { data } = await api.post(`/deals/${id}/decision`, null, {
    params: { decision },
  });
  return data;
}

export default api;
