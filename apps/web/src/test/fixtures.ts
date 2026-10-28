import type { Comp, Item, ItemMarket, SyncJob } from "../api/types";

export function makeItem(overrides: Partial<Item> = {}, card: Partial<Item["card"]> = {}): Item {
  return {
    id: "item-1",
    card: {
      variant_id: "variant-1",
      set_id: "set-1",
      sport: "baseball",
      brand: "bowman",
      year: 2025,
      set_name: "Bowman Chrome",
      card_number: "CPA-JW",
      name: "JJ Wetherholt",
      subset: "Chrome Prospect Autographs",
      team: "Cardinals",
      players: ["JJ Wetherholt"],
      parallel: {
        id: "par-1",
        name: "Gold Refractor",
        subset: "Chrome Prospect Autographs",
        print_run: 50,
        color: null,
      },
      is_rookie: false,
      is_autograph: true,
      is_memorabilia: false,
      ...card,
    },
    condition: "raw",
    grader: null,
    grade: null,
    cert_number: null,
    serial_number: 12,
    purchase_price: { amount: "250.00", currency: "USD" },
    acquired_on: "2026-05-01",
    notes: null,
    estimated_value: null,
    estimate: null,
    images: { front: null, back: null },
    created_at: "2026-10-26T12:00:00Z",
    updated_at: "2026-10-26T12:00:00Z",
    ...overrides,
  };
}

export function makeMarket(overrides: Partial<ItemMarket> = {}): ItemMarket {
  return {
    item_id: "item-1",
    grade: "PSA 10",
    estimate: null,
    comps: [],
    asks: [],
    last_sync: null,
    ...overrides,
  };
}

export function makeComp(overrides: Partial<Comp> = {}): Comp {
  return {
    id: "sale-1",
    sold_at: "2026-10-20T12:00:00Z",
    price: { amount: "95.00", currency: "USD" },
    condition: "graded",
    grader: "PSA",
    grade: "10.0",
    title: "2025 Bowman Chrome JJ Wetherholt Gold /50 PSA 10",
    url: null,
    source: "fixture",
    sale_type: "auction",
    match: "exact",
    mine: false,
    ...overrides,
  };
}

export function makeJob(overrides: Partial<SyncJob> = {}): SyncJob {
  return {
    id: "job-1",
    status: "queued",
    created_at: "2026-10-27T12:00:00Z",
    started_at: null,
    finished_at: null,
    error: null,
    ...overrides,
  };
}
