import { describe, expect, it } from 'vitest';
import { OSM_ATTRIBUTION, OSM_TILE_URL, getMapConfig, tileLayerOptions } from './mapConfig';

describe('map tile config', () => {
  it('defaults to the public OSM endpoint and forbids prefetch', () => {
    const config = getMapConfig();
    expect(config.tileUrl).toBe(OSM_TILE_URL);
    expect(config.tileUrl).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    expect(config.attribution).toBe(OSM_ATTRIBUTION);

    const options = tileLayerOptions(config.attribution, config.attributionUrl);
    expect(options).not.toHaveProperty('prefetch');
    expect(options.keepBuffer).toBe(0);
    expect(options.detectRetina).toBe(false);
    expect(options.updateWhenIdle).toBe(true);
    expect(options.updateWhenZooming).toBe(false);
    expect(options.maxZoom).toBe(19);
    expect(options.attribution).toContain('https://www.openstreetmap.org/copyright');
    expect(options.attribution).toContain('© OpenStreetMap contributors');
  });
});
