import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import SearchPage from './Search';

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderSearch(path = '/search') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/search"
            element={
              <>
                <SearchPage />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Search page', () => {
  it('groups the BaT and eBay listing of the same car and shows each price drop', async () => {
    renderSearch();

    const m3 = await screen.findByRole('article', { name: /2003 BMW M3/i });
    expect(screen.getAllByRole('article', { name: /BMW M3/i })).toHaveLength(1);
    expect(within(m3).getByText('Bring a Trailer')).toBeInTheDocument();
    expect(within(m3).getByText('eBay')).toBeInTheDocument();
    expect(within(m3).getAllByText('$31,200').length).toBeGreaterThan(0);
    expect(within(m3).getByText('$32,950')).toBeInTheDocument();
    expect(within(m3).getByText('down from $34,800')).toBeInTheDocument();
    expect(within(m3).getByText('down from $33,900')).toBeInTheDocument();

    expect(screen.getByRole('article', { name: /1993 Mazda RX-7/i })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: /1991 Acura Legend/i })).toBeInTheDocument();
    expect(screen.getByText(/5bc43fe/)).toBeInTheDocument();
    expect(screen.getByText(/no zip field/i)).toBeInTheDocument();
  });

  it('loads filters from the URL and shows the matching car', async () => {
    renderSearch('/search?make=Mazda&model=RX-7&year_min=1990&year_max=1995&mileage_max=90000');

    expect(screen.getByLabelText('Make')).toHaveValue('Mazda');
    expect(screen.getByLabelText('Model')).toHaveValue('RX-7');
    expect(screen.getByLabelText('Year from')).toHaveValue('1990');
    expect(screen.getByLabelText('Year to')).toHaveValue('1995');
    expect(screen.getByLabelText('Max mileage')).toHaveValue('90000');

    expect(await screen.findByRole('article', { name: /RX-7/i })).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: /BMW M3/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: /Legend/i })).not.toBeInTheDocument();
  });

  it('writes filters to the URL and narrows the list', async () => {
    const user = userEvent.setup();
    renderSearch();
    await screen.findByRole('article', { name: /Legend/i });

    await user.type(screen.getByLabelText('Make'), 'BMW');
    await user.type(screen.getByLabelText('Max mileage'), '70000');
    await user.type(screen.getByLabelText('Location'), 'Austin, TX');
    await user.type(screen.getByLabelText('Radius'), '50');
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    const href = screen.getByTestId('location').textContent ?? '';
    expect(href).toContain('make=BMW');
    expect(href).toContain('mileage_max=70000');
    expect(href).toContain('location=Austin');
    expect(href).toContain('radius=50');

    expect(await screen.findByRole('article', { name: /BMW M3/i })).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: /RX-7/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: /Legend/i })).not.toBeInTheDocument();
  });

  it('reads the sort query and explains that deal score is not on the model', async () => {
    renderSearch('/search?sort=deal');
    expect(screen.getByLabelText('Sort')).toHaveValue('deal');
    expect(await screen.findByText(/deal score is not on the listing model/i)).toBeInTheDocument();
    const articles = await screen.findAllByRole('article');
    expect(articles[0]).toHaveAccessibleName(/Acura Legend/);
  });
});
