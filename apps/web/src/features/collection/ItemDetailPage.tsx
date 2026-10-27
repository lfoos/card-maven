import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError } from "../../api/errors";
import { formatGrade, formatMoney, parallelLine, setLine, sportLabel } from "../../lib/format";
import { PhotoSlot } from "./PhotoSlot";
import { useDeleteItem, useItem } from "./queries";

export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const query = useItem(itemId);
  const remove = useDeleteItem();
  const [confirming, setConfirming] = useState(false);

  if (query.isPending) return <p className="muted">Loading…</p>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <section className="page">
        <div role="alert" className="notice notice--error">
          <p>{missing ? "That card isn't in your collection." : "Couldn't load this card."}</p>
          <Link to="/collection">Back to collection</Link>
        </div>
      </section>
    );
  }

  const item = query.data;
  const { card } = item;
  const rows: [string, string][] = [
    ["Sport", sportLabel(card.sport)],
    ["Set", setLine(item)],
    ["Parallel", parallelLine(item) ?? "Base"],
    ["Players", card.players.join(", ") || "—"],
    ["Team", card.team ?? "—"],
    ["Subset", card.subset ?? "—"],
    ["Grade", formatGrade(item) + (item.cert_number ? ` · cert ${item.cert_number}` : "")],
    ["Paid", formatMoney(item.purchase_price)],
    ["Acquired", item.acquired_on ?? "—"],
    ["Estimated value", formatMoney(item.estimated_value)],
  ];
  const flags = [
    card.is_rookie && "Rookie",
    card.is_autograph && "Autograph",
    card.is_memorabilia && "Memorabilia",
  ].filter(Boolean);

  async function handleDelete() {
    await remove.mutateAsync(item.id);
    void navigate("/collection", { replace: true });
  }

  return (
    <section className="page detail">
      <p>
        <Link to="/collection">← Collection</Link>
      </p>
      <header className="page__header">
        <div>
          <h1>{card.name}</h1>
          <p className="lede">{setLine(item)}</p>
          {flags.length ? (
            <p className="tile__badges">
              {flags.map((f) => (
                <span key={String(f)} className="badge">
                  {f}
                </span>
              ))}
            </p>
          ) : null}
        </div>
        <div className="page__actions">
          <Link to={`/collection/${item.id}/edit`} className="button button--quiet">
            Edit
          </Link>
          <button
            type="button"
            className="button button--danger"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        </div>
      </header>

      {confirming ? (
        <div role="alertdialog" aria-labelledby="confirm-title" className="notice notice--error">
          <p id="confirm-title">Delete this card and its photos? This can't be undone.</p>
          <div className="form-actions">
            <button
              type="button"
              className="button button--quiet"
              onClick={() => setConfirming(false)}
            >
              Keep it
            </button>
            <button
              type="button"
              className="button button--danger"
              onClick={() => void handleDelete()}
              disabled={remove.isPending}
            >
              {remove.isPending ? "Deleting…" : "Delete card"}
            </button>
          </div>
          {remove.isError ? (
            <p className="field__error">Couldn't delete the card. Please try again.</p>
          ) : null}
        </div>
      ) : null}

      <div className="detail__layout">
        <div className="photos">
          <PhotoSlot item={item} kind="front" />
          <PhotoSlot item={item} kind="back" />
        </div>
        <dl className="facts">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
          {item.notes ? (
            <div>
              <dt>Notes</dt>
              <dd>{item.notes}</dd>
            </div>
          ) : null}
        </dl>
      </div>
    </section>
  );
}
