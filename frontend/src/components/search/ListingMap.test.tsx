import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OSM_COPYRIGHT_URL } from '../../config/mapConfig';
import { fixtureListings } from '../../fixtures/listings';
import { groupListings } from '../../lib/groupListings';
import ListingMap from './ListingMap.tsx';

const groups = groupListings(fixtureListings());

describe('ListingMap', () => {
  it('renders the OpenStreetMap attribution link', () => {
    render(<ListingMap groups={groups} selectedKey={null} onSelect={() => {}} />);

    const link = screen.getByRole('link', { name: '© OpenStreetMap contributors' });
    expect(link).toHaveAttribute('href', OSM_COPYRIGHT_URL);
    expect(link).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
    expect(link.closest('[data-testid="listing-map"]')).not.toBeNull();
  });

  it('skips listings that have no coordinates', () => {
    render(<ListingMap groups={groups} selectedKey={null} onSelect={() => {}} />);

    expect(screen.getByRole('region', { name: 'Map showing 1 listing' })).toBeInTheDocument();
    const skipped = screen.getByRole('status');
    expect(skipped).toHaveTextContent(/no coordinates/i);
    expect(skipped).toHaveTextContent('1993 Mazda RX-7 Touring');
    expect(skipped).toHaveTextContent('1991 Acura Legend L');
    expect(skipped).not.toHaveTextContent('BMW M3');
  });
});
