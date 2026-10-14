/**
 * source_for catalog from PR #8 @ 5bc43fe. Crawl flags stay false.
 */

import type { SellerType, Source, SourceCode } from '../types/listing';

const CATALOG: Record<SourceCode, { kind: SellerType; name: string; base_url: string }> = {
  bat: { kind: 'auction', name: 'Bring a Trailer', base_url: 'https://bringatrailer.com' },
  cab: { kind: 'auction', name: 'Cars and Bids', base_url: 'https://carsandbids.com' },
  ebay: { kind: 'marketplace', name: 'eBay', base_url: 'https://www.ebay.com' },
  classic_com: { kind: 'marketplace', name: 'Classic.com', base_url: 'https://www.classic.com' },
  tcv: { kind: 'auction', name: 'TCV', base_url: 'https://www.tc-v.com' },
  facebook: {
    kind: 'marketplace',
    name: 'Facebook Marketplace',
    base_url: 'https://www.facebook.com/marketplace',
  },
  autotrader: { kind: 'dealer', name: 'Autotrader', base_url: 'https://www.autotrader.com' },
  hemmings: { kind: 'marketplace', name: 'Hemmings', base_url: 'https://www.hemmings.com' },
  craigslist: { kind: 'marketplace', name: 'Craigslist', base_url: 'https://www.craigslist.org' },
  manual: { kind: 'marketplace', name: 'Manual', base_url: 'https://example.com/manual' },
};

export function sourceFor(code: SourceCode): Source {
  const meta = CATALOG[code];
  return {
    code,
    kind: meta.kind,
    name: meta.name,
    base_url: meta.base_url,
    robots_ok: false,
    tos_reviewed: false,
  };
}
