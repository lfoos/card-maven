import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import type { ItemMarket } from "../../api/types";
import { makeComp, makeJob, makeMarket } from "../../test/fixtures";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { MarketPanel } from "./MarketPanel";

type Handler = Parameters<typeof fakeClient>[0];

function render(handler: Handler) {
  const fake = fakeClient(handler);
  renderWithApi(fake.client, { element: <MarketPanel itemId="item-1" /> });
  return fake;
}

const COMPS = "/api/v1/collection/items/item-1/comps";

const FULL: ItemMarket = makeMarket({
  estimate: {
    value: { amount: "98.75", currency: "USD" },
    sample_size: 2,
    grade: "PSA 10",
    window_days: 180,
    latest_sale_at: "2026-10-20T12:00:00Z",
  },
  comps: [
    makeComp({ url: "https://www.ebay.com/itm/1" }),
    makeComp({
      id: "sale-2",
      grade: "9.0",
      match: "nearest",
      price: { amount: "41.00", currency: "USD" },
    }),
    makeComp({ id: "sale-3", source: "manual", mine: true, sold_at: "2026-10-01T12:00:00Z" }),
  ],
  asks: [
    {
      id: "ask-1",
      title: "JJ Wetherholt Gold /50 PSA 10",
      price: { amount: "120.00", currency: "USD" },
      buying_option: "auction",
      bid_count: 3,
      condition: "graded",
      grader: "PSA",
      grade: "10.0",
      url: "https://www.ebay.com/itm/9?campid=1",
      image_url: null,
      source: "ebay_browse",
      observed_at: new Date().toISOString(),
      ends_at: null,
    },
  ],
  last_sync: makeJob({ status: "succeeded", finished_at: new Date().toISOString() }),
});

describe("MarketPanel", () => {
  it("shows the estimate with its basis, comps, and asks", async () => {
    render(() => FULL);
    expect(await screen.findByText("$98.75")).toBeInTheDocument();
    expect(
      screen.getByText("Median of 2 PSA 10 sales in the last 180 days · latest Oct 20, 2026"),
    ).toBeInTheDocument();
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(within(rows[2]!).getByText("nearest")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sample data" })).toHaveAttribute(
      "rel",
      "noopener noreferrer nofollow",
    );
    const ask = screen.getByRole("link", { name: "JJ Wetherholt Gold /50 PSA 10" });
    expect(ask).toHaveAttribute("rel", "sponsored noopener noreferrer");
    expect(screen.getByText(/eBay · PSA 10 · 3 bids · seen just now/)).toBeInTheDocument();
    expect(screen.getByText(/Asking prices, not sales/)).toHaveTextContent(/may earn a commission/);
    expect(screen.getByRole("status")).toHaveTextContent("Updated just now");
    // Only your own manual sale can be deleted.
    expect(screen.getAllByRole("button", { name: /Delete your/ })).toHaveLength(1);
  });

  it("explains an empty market", async () => {
    render(() => makeMarket({ grade: "Raw" }));
    expect(
      await screen.findByText("No recent Raw sales yet, so there's no estimate."),
    ).toBeInTheDocument();
    expect(screen.getByText("No sales found for this card yet.")).toBeInTheDocument();
    expect(screen.getByText("No current listings found.")).toBeInTheDocument();
    expect(screen.getByText(/Not synced yet/)).toBeInTheDocument();
  });

  it("reports a load failure", async () => {
    render(() => {
      throw new ApiError(500, "internal_error", "Oops");
    });
    expect(await screen.findByText("Couldn't load market data.")).toBeInTheDocument();
  });

  it("gets comps: starts a sync, polls until done, then reloads", async () => {
    let synced = false;
    const { request } = render((path, options) => {
      if (path.endsWith("/comps/refresh")) return makeJob();
      if (path.startsWith("/api/v1/market/sync-jobs/")) {
        synced = true;
        return makeJob({ status: "succeeded", finished_at: new Date().toISOString() });
      }
      if (path === COMPS && options?.method === "GET") return synced ? FULL : makeMarket();
      throw new Error(`unexpected ${path}`);
    });
    await userEvent.click(await screen.findByRole("button", { name: "Get comps" }));
    expect(await screen.findByText("$98.75")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Get comps" })).toBeEnabled();
    expect(request).toHaveBeenCalledWith("/api/v1/market/sync-jobs/job-1", { method: "GET" });
  });

  it("keeps polling while the sync runs", async () => {
    let polls = 0;
    render((path) => {
      if (path.endsWith("/comps/refresh")) return makeJob();
      if (path.startsWith("/api/v1/market/sync-jobs/")) {
        polls += 1;
        return polls < 2 ? makeJob({ status: "running" }) : makeJob({ status: "failed" });
      }
      return makeMarket();
    });
    await userEvent.click(await screen.findByRole("button", { name: "Get comps" }));
    expect(await screen.findByText("Checking market sources…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Getting comps…" })).toBeDisabled();
    expect(
      await screen.findByText("The last sync failed. Showing what we already have.", undefined, {
        timeout: 4000,
      }),
    ).toBeInTheDocument();
    expect(polls).toBe(2);
  });

  it("explains rate limiting", async () => {
    render((path) => {
      if (path.endsWith("/comps/refresh")) {
        throw new ApiError(429, "too_many_requests", "Too many requests");
      }
      return makeMarket();
    });
    await userEvent.click(await screen.findByRole("button", { name: "Get comps" }));
    expect(
      await screen.findByText("Too many requests. Try again in a minute."),
    ).toBeInTheDocument();
  });

  it("adds a single graded sale", async () => {
    const { request } = render((path, options) => {
      if (path === COMPS && options?.method === "POST") {
        return { added: 1, market: FULL };
      }
      return makeMarket();
    });
    await userEvent.click(await screen.findByText("Add sales you know of"));
    await userEvent.type(screen.getByLabelText("Date sold"), "2026-10-01");
    await userEvent.type(screen.getByLabelText("Price (USD)"), "$1,050.00");
    await userEvent.selectOptions(screen.getByLabelText("Grader"), "PSA");
    await userEvent.type(screen.getByLabelText("Grade"), "9");
    await userEvent.type(screen.getByLabelText("Note (optional)"), " card show ");
    await userEvent.click(screen.getByRole("button", { name: "Add sale" }));
    expect(await screen.findByText("Added 1 sale.")).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith(COMPS, {
      method: "POST",
      body: {
        sales: [
          {
            sold_on: "2026-10-01",
            price: { amount: "1050.00", currency: "USD" },
            condition: "graded",
            grader: "PSA",
            grade: "9",
            title: "card show",
          },
        ],
      },
    });
    expect(screen.getByLabelText("Date sold")).toHaveValue("");
  });

  it("imports CSV, and shows parse and server errors", async () => {
    let posts = 0;
    const { request } = render((path, options) => {
      if (path === COMPS && options?.method === "POST") {
        posts += 1;
        if (posts === 1) {
          throw new ApiError(422, "invalid_input", "Invalid input", {
            title: "Invalid input",
            status: 422,
            code: "invalid_input",
            errors: [{ loc: "sales.0.sold_on", message: "can't be in the future" }],
          });
        }
        return { added: 2, market: makeMarket() };
      }
      return makeMarket();
    });
    await userEvent.click(await screen.findByText("Add sales you know of"));
    const box = screen.getByLabelText(/Or paste CSV/);

    await userEvent.type(box, "date,price{enter}nope,5");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText('Line 2: "nope" isn\'t a date.')).toBeInTheDocument();
    expect(request).not.toHaveBeenCalledWith(COMPS, expect.objectContaining({ method: "POST" }));

    await userEvent.clear(box);
    await userEvent.type(box, "date,price{enter}2026-10-01,5{enter}2026-10-02,6");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Sale 1 (sold_on): can't be in the future")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Added 2 sales.")).toBeInTheDocument();
    await waitFor(() => expect(box).toHaveValue(""));
  });

  it("loads CSV from a file", async () => {
    render(() => makeMarket());
    await userEvent.click(await screen.findByText("Add sales you know of"));
    const file = new File(["date,price\n2026-10-01,5"], "sales.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Choose file"), file);
    await waitFor(() =>
      expect(screen.getByLabelText(/Or paste CSV/)).toHaveValue("date,price\n2026-10-01,5"),
    );
  });

  it("refuses oversized files", async () => {
    render(() => makeMarket());
    await userEvent.click(await screen.findByText("Add sales you know of"));
    const big = new File(["x".repeat(1_000_001)], "big.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Choose file"), big);
    expect(await screen.findByText("That file is over 1 MB. Split it up.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Or paste CSV/)).toHaveValue("");
  });

  it("deletes your own sale", async () => {
    let deleted = false;
    const { request } = render((_path, options) => {
      if (options?.method === "DELETE") {
        deleted = true;
        return undefined;
      }
      return deleted ? makeMarket() : FULL;
    });
    await userEvent.click(await screen.findByRole("button", { name: /Delete your/ }));
    expect(request).toHaveBeenCalledWith("/api/v1/market/sales/sale-3", { method: "DELETE" });
    expect(await screen.findByText("No sales found for this card yet.")).toBeInTheDocument();
  });

  it("reports a failed delete", async () => {
    render((_path, options) => {
      if (options?.method === "DELETE") throw new ApiError(404, "not_found", "Not found");
      return FULL;
    });
    await userEvent.click(await screen.findByRole("button", { name: /Delete your/ }));
    expect(await screen.findByText("Couldn't delete that sale.")).toBeInTheDocument();
  });
});
