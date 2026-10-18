/**
 * Map tiles. Defaults follow the OSM tile usage policy:
 * https://operations.osmfoundation.org/policies/tiles/
 * No API key. Swap the Vite env vars before shipping a public app.
 * The browser requests only the tiles in view. Do not prefetch or bulk-download.
 */

export const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const OSM_ATTRIBUTION = '© OpenStreetMap contributors';
export const OSM_COPYRIGHT_URL = 'https://www.openstreetmap.org/copyright';

export type MapConfig = {
  tileUrl: string;
  attribution: string;
  attributionUrl: string;
};

function envValue(name: 'VITE_MAP_TILE_URL' | 'VITE_MAP_ATTRIBUTION'): string {
  const value = import.meta.env[name];
  return typeof value === 'string' ? value.trim() : '';
}

export function getMapConfig(): MapConfig {
  return {
    tileUrl: envValue('VITE_MAP_TILE_URL') || OSM_TILE_URL,
    attribution: envValue('VITE_MAP_ATTRIBUTION') || OSM_ATTRIBUTION,
    attributionUrl: OSM_COPYRIGHT_URL,
  };
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

/** Viewport tiles only. keepBuffer 0 and no retina doubling avoid extra tile fetches. */
export function tileLayerOptions(attribution: string, attributionUrl: string) {
  return {
    attribution: `<a href="${escapeHtml(attributionUrl)}">${escapeHtml(attribution)}</a>`,
    maxZoom: 19,
    updateWhenIdle: true,
    updateWhenZooming: false,
    keepBuffer: 0,
    detectRetina: false,
  };
}
