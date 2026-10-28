import { useState, type ChangeEvent, type FormEvent } from "react";
import { ApiError } from "../../api/errors";
import type { Ask, Comp, Grader, ItemMarket, ManualSale, SyncJob } from "../../api/types";
import { formatAge, formatDate, formatGrade, formatMoney, sourceLabel } from "../../lib/format";
import { saveError } from "./saleErrors";
import { MAX_CSV_BYTES, MAX_SALES, parseSalesCsv } from "./salesCsv";
import { useAddSales, useDeleteSale, useGetComps, useItemMarket } from "./queries";

const GRADERS: Grader[] = ["PSA", "BGS", "SGC", "CGC", "TAG"];

/** Comps, estimate, and current asks for one collection item. */
export function MarketPanel({ itemId }: { itemId: string }) {
  const market = useItemMarket(itemId);
  const comps = useGetComps(itemId);

  return (
    <section className="market" aria-labelledby="market-title">
      <header className="market__header">
        <h2 id="market-title">Market</h2>
        <button type="button" className="button" onClick={comps.start} disabled={comps.working}>
          {comps.working ? "Getting comps…" : "Get comps"}
        </button>
      </header>
      <SyncStatus job={comps.job ?? market.data?.last_sync ?? null} error={comps.error} />

      {market.isPending ? <p className="muted">Loading market data…</p> : null}
      {market.isError ? (
        <p role="alert" className="notice notice--error">
          Couldn't load market data.
        </p>
      ) : null}
      {market.data ? <MarketDetails itemId={itemId} market={market.data} /> : null}
    </section>
  );
}

function SyncStatus({ job, error }: { job: SyncJob | null; error: Error | null }) {
  if (error) {
    const limited = error instanceof ApiError && error.status === 429;
    return (
      <p role="alert" className="field__error">
        {limited ? "Too many requests. Try again in a minute." : "Couldn't start a market sync."}
      </p>
    );
  }
  if (!job) return <p className="muted">Not synced yet. Get comps to check market sources.</p>;
  if (job.status === "queued" || job.status === "running") {
    return (
      <p className="muted" role="status">
        Checking market sources…
      </p>
    );
  }
  if (job.status === "failed") {
    return (
      <p role="alert" className="field__error">
        The last sync failed. Showing what we already have.
      </p>
    );
  }
  return (
    <p className="muted" role="status">
      Updated {formatAge(job.finished_at ?? job.created_at)}
    </p>
  );
}

function MarketDetails({ itemId, market }: { itemId: string; market: ItemMarket }) {
  const { estimate } = market;
  return (
    <>
      <div className="market__estimate">
        <p className="market__value">{estimate ? formatMoney(estimate.value) : "—"}</p>
        <p className="muted">
          {estimate
            ? `Median of ${estimate.sample_size} ${estimate.grade} sale${estimate.sample_size === 1 ? "" : "s"} in the last ${estimate.window_days} days · latest ${formatDate(estimate.latest_sale_at)}`
            : `No recent ${market.grade} sales yet, so there's no estimate.`}
        </p>
      </div>

      <h3>Recent sales</h3>
      {market.comps.length ? (
        <CompsTable itemId={itemId} comps={market.comps} />
      ) : (
        <p className="muted">No sales found for this card yet.</p>
      )}

      <h3>Current listings</h3>
      <p className="muted">
        Asking prices, not sales. They never affect the estimate. Card Maven may earn a commission
        from listing links.
      </p>
      {market.asks.length ? (
        <ul className="asks">
          {market.asks.map((ask) => (
            <AskRow key={ask.id} ask={ask} />
          ))}
        </ul>
      ) : (
        <p className="muted">No current listings found.</p>
      )}

      <AddSales itemId={itemId} />
    </>
  );
}

function CompsTable({ itemId, comps }: { itemId: string; comps: Comp[] }) {
  const remove = useDeleteSale(itemId);
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Sold</th>
            <th scope="col" className="num">
              Price
            </th>
            <th scope="col">Grade</th>
            <th scope="col">Source</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {comps.map((comp) => (
            <tr key={comp.id}>
              <td>{formatDate(comp.sold_at)}</td>
              <td className="num">{formatMoney(comp.price)}</td>
              <td>
                {formatGrade(comp)}
                {comp.match === "nearest" ? (
                  <span className="badge" title="No sale at your exact grade; closest shown">
                    nearest
                  </span>
                ) : null}
              </td>
              <td>
                {comp.url ? (
                  <a href={comp.url} target="_blank" rel="noopener noreferrer nofollow">
                    {sourceLabel(comp.source)}
                  </a>
                ) : (
                  sourceLabel(comp.source)
                )}
              </td>
              <td>
                {comp.mine ? (
                  <button
                    type="button"
                    className="button button--quiet"
                    onClick={() => remove.mutate(comp.id)}
                    disabled={remove.isPending}
                    aria-label={`Delete your ${formatDate(comp.sold_at)} sale`}
                  >
                    Delete
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {remove.isError ? <p className="field__error">Couldn't delete that sale.</p> : null}
    </div>
  );
}

function AskRow({ ask }: { ask: Ask }) {
  const bids = ask.buying_option === "auction" ? ` · ${ask.bid_count ?? 0} bids` : "";
  return (
    <li className="asks__row">
      <span className="asks__price">{formatMoney(ask.price)}</span>
      <span className="asks__title">
        {ask.url ? (
          // Affiliate links: marked sponsored, per search-engine and FTC guidance.
          <a href={ask.url} target="_blank" rel="sponsored noopener noreferrer">
            {ask.title}
          </a>
        ) : (
          ask.title
        )}
      </span>
      <span className="muted">
        {sourceLabel(ask.source)} · {formatGrade(ask)}
        {bids} · seen {formatAge(ask.observed_at)}
      </span>
    </li>
  );
}

interface SaleDraft {
  sold_on: string;
  amount: string;
  grader: "" | Grader;
  grade: string;
  title: string;
  url: string;
}

const EMPTY_DRAFT: SaleDraft = {
  sold_on: "",
  amount: "",
  grader: "",
  grade: "",
  title: "",
  url: "",
};

function draftToSale(draft: SaleDraft): ManualSale {
  const sale: ManualSale = {
    sold_on: draft.sold_on,
    price: { amount: draft.amount.replace(/[$,\s]/g, ""), currency: "USD" },
    condition: draft.grader ? "graded" : "raw",
  };
  if (draft.grader) Object.assign(sale, { grader: draft.grader, grade: draft.grade });
  if (draft.title.trim()) sale.title = draft.title.trim();
  if (draft.url.trim()) sale.url = draft.url.trim();
  return sale;
}

function AddSales({ itemId }: { itemId: string }) {
  const add = useAddSales(itemId);
  const [draft, setDraft] = useState<SaleDraft>(EMPTY_DRAFT);
  const [csv, setCsv] = useState("");
  const [csvErrors, setCsvErrors] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const set = (key: keyof SaleDraft) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft({ ...draft, [key]: e.target.value });

  function submit(sales: ManualSale[], onDone: () => void) {
    setMessage(null);
    add.mutate(sales, {
      onSuccess: (result) => {
        setMessage(`Added ${result.added} sale${result.added === 1 ? "" : "s"}.`);
        onDone();
      },
    });
  }

  function handleSingle(event: FormEvent) {
    event.preventDefault();
    submit([draftToSale(draft)], () => setDraft(EMPTY_DRAFT));
  }

  function handleCsv(event: FormEvent) {
    event.preventDefault();
    const parsed = parseSalesCsv(csv);
    setCsvErrors(parsed.errors);
    if (parsed.errors.length === 0 && parsed.sales.length) submit(parsed.sales, () => setCsv(""));
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_CSV_BYTES) {
      setCsvErrors([`That file is over ${MAX_CSV_BYTES / 1_000_000} MB. Split it up.`]);
      return;
    }
    setCsvErrors([]);
    setCsv(await file.text());
  }

  return (
    <details className="market__add">
      <summary>Add sales you know of</summary>
      <p className="muted">Only you see these. They count toward your comps and estimate.</p>
      <form onSubmit={handleSingle} className="form-grid" aria-label="Add one sale">
        <div className="field">
          <label htmlFor="sale-date">Date sold</label>
          <input
            id="sale-date"
            type="date"
            required
            value={draft.sold_on}
            onChange={set("sold_on")}
          />
        </div>
        <div className="field">
          <label htmlFor="sale-price">Price (USD)</label>
          <input
            id="sale-price"
            inputMode="decimal"
            required
            pattern="\$?[0-9,]+(\.[0-9]{1,2})?"
            value={draft.amount}
            onChange={set("amount")}
          />
        </div>
        <div className="field">
          <label htmlFor="sale-grader">Grader</label>
          <select id="sale-grader" value={draft.grader} onChange={set("grader")}>
            <option value="">Raw (ungraded)</option>
            {GRADERS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        {draft.grader ? (
          <div className="field">
            <label htmlFor="sale-grade">Grade</label>
            <input
              id="sale-grade"
              inputMode="decimal"
              required
              value={draft.grade}
              onChange={set("grade")}
            />
          </div>
        ) : null}
        <div className="field field--wide">
          <label htmlFor="sale-title">Note (optional)</label>
          <input id="sale-title" maxLength={300} value={draft.title} onChange={set("title")} />
        </div>
        <div className="field field--wide">
          <label htmlFor="sale-url">Link (optional)</label>
          <input id="sale-url" type="url" value={draft.url} onChange={set("url")} />
        </div>
        <div className="form-actions">
          <button type="submit" className="button" disabled={add.isPending}>
            Add sale
          </button>
        </div>
      </form>

      <form onSubmit={handleCsv} aria-label="Import sales from CSV">
        <div className="field field--full">
          <label htmlFor="sale-csv">Or paste CSV (up to {MAX_SALES} rows)</label>
          <textarea
            id="sale-csv"
            rows={5}
            placeholder={"date,price,grader,grade,title\n2026-10-01,95.00,PSA,10,eBay auction"}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
          />
          <span className="field__hint">
            Columns: date, price, and optionally currency, grader, grade, title, url, type.
          </span>
        </div>
        <div className="form-actions">
          <label className="button button--quiet">
            Choose file
            <input
              type="file"
              accept=".csv,text/csv"
              className="visually-hidden"
              onChange={(e) => void handleFile(e)}
            />
          </label>
          <button type="submit" className="button" disabled={add.isPending || !csv.trim()}>
            Import
          </button>
        </div>
        {csvErrors.length ? (
          <ul role="alert" className="field__error">
            {csvErrors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        ) : null}
      </form>
      {add.isError ? (
        <p role="alert" className="field__error">
          {saveError(add.error)}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="muted">
          {message}
        </p>
      ) : null}
    </details>
  );
}
