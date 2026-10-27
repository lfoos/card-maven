import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import type { Condition, ItemFilters, ItemSort } from "../../api/types";
import { SPORT_OPTIONS } from "../../lib/format";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { ItemGrid, ItemTable } from "./ItemViews";
import { useItems } from "./queries";

const SORTS: { value: ItemSort; label: string }[] = [
  { value: "newest", label: "Recently added" },
  { value: "oldest", label: "Oldest added" },
  { value: "year_desc", label: "Year (newest)" },
  { value: "year_asc", label: "Year (oldest)" },
  { value: "name", label: "Name A–Z" },
];

/** Filters live in the URL, so views are shareable and survive reloads. */
function useFilters() {
  const [params, setParams] = useSearchParams();
  const filters: ItemFilters = {};
  const q = params.get("q");
  if (q) filters.q = q;
  const sport = params.get("sport");
  if (sport) filters.sport = sport;
  const year = Number(params.get("year"));
  if (Number.isInteger(year) && year > 0) filters.year = year;
  const condition = params.get("condition");
  if (condition === "raw" || condition === "graded") filters.condition = condition;
  const sort = params.get("sort") as ItemSort | null;
  if (sort && SORTS.some((s) => s.value === sort)) filters.sort = sort;
  const view = params.get("view") === "table" ? "table" : "grid";

  function update(changes: Record<string, string | undefined>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  }
  return { filters, view, update };
}

export function CollectionPage() {
  const { filters, view, update } = useFilters();
  const [search, setSearch] = useState(filters.q ?? "");
  const debouncedSearch = useDebouncedValue(search, 300);
  useEffect(() => {
    if ((filters.q ?? "") !== debouncedSearch.trim())
      update({ q: debouncedSearch.trim() || undefined });
    // Only react to the user's typing, not to URL changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const query = useItems(filters);
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const filtering = Boolean(filters.q || filters.sport || filters.year || filters.condition);

  return (
    <section className="page">
      <header className="page__header">
        <h1>Collection</h1>
        <Link to="/collection/new" className="button">
          Add card
        </Link>
      </header>

      <div className="toolbar" role="search">
        <input
          type="search"
          aria-label="Search your cards"
          placeholder="Search player, set, team, parallel…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Sport"
          value={filters.sport ?? ""}
          onChange={(e) => update({ sport: e.target.value })}
        >
          <option value="">All sports</option>
          {SPORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Year"
          inputMode="numeric"
          placeholder="Year"
          className="toolbar__year"
          defaultValue={filters.year ?? ""}
          onBlur={(e) =>
            update({ year: /^\d{4}$/.test(e.target.value) ? e.target.value : undefined })
          }
        />
        <select
          aria-label="Condition"
          value={filters.condition ?? ""}
          onChange={(e) => update({ condition: (e.target.value as Condition) || undefined })}
        >
          <option value="">Raw & graded</option>
          <option value="raw">Raw</option>
          <option value="graded">Graded</option>
        </select>
        <select
          aria-label="Sort"
          value={filters.sort ?? "newest"}
          onChange={(e) => update({ sort: e.target.value })}
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <div className="segmented" role="group" aria-label="View">
          <button
            type="button"
            aria-pressed={view === "grid"}
            onClick={() => update({ view: undefined })}
          >
            Grid
          </button>
          <button
            type="button"
            aria-pressed={view === "table"}
            onClick={() => update({ view: "table" })}
          >
            Table
          </button>
        </div>
      </div>

      {query.isPending ? (
        <p className="muted" aria-live="polite">
          Loading your cards…
        </p>
      ) : query.isError ? (
        <div role="alert" className="notice notice--error">
          <p>Couldn't load your collection.</p>
          <button type="button" className="button" onClick={() => void query.refetch()}>
            Try again
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          {filtering ? (
            <p>No cards match these filters.</p>
          ) : (
            <>
              <p>No cards yet.</p>
              <Link to="/collection/new" className="button">
                Add your first card
              </Link>
            </>
          )}
        </div>
      ) : (
        <>
          {view === "table" ? <ItemTable items={items} /> : <ItemGrid items={items} />}
          {query.hasNextPage ? (
            <div className="load-more">
              <button
                type="button"
                className="button button--quiet"
                onClick={() => void query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
