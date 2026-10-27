import { Link } from "react-router";
import type { Item } from "../../api/types";
import { formatGrade, formatMoney, parallelLine, setLine, sportLabel } from "../../lib/format";

function Thumb({ item }: { item: Item }) {
  const front = item.images.front;
  return front ? (
    <img
      className="tile__image"
      src={front.url}
      alt={`Front of ${item.card.name}`}
      loading="lazy"
    />
  ) : (
    <div className="tile__image tile__image--empty" aria-hidden="true">
      {item.card.card_number}
    </div>
  );
}

export function ItemGrid({ items }: { items: Item[] }) {
  return (
    <ul className="grid" aria-label="Cards">
      {items.map((item) => {
        const parallel = parallelLine(item);
        return (
          <li key={item.id}>
            <Link to={`/collection/${item.id}`} className="tile">
              <Thumb item={item} />
              <div className="tile__body">
                <p className="tile__title">{item.card.name}</p>
                <p className="tile__meta">{setLine(item)}</p>
                <p className="tile__badges">
                  {parallel ? <span className="badge badge--accent">{parallel}</span> : null}
                  <span className="badge">{formatGrade(item)}</span>
                  {item.card.is_rookie ? <span className="badge">RC</span> : null}
                  {item.card.is_autograph ? <span className="badge">Auto</span> : null}
                </p>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function ItemTable({ items }: { items: Item[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Card</th>
            <th scope="col">Sport</th>
            <th scope="col">Year</th>
            <th scope="col">Set</th>
            <th scope="col">#</th>
            <th scope="col">Parallel</th>
            <th scope="col">Team</th>
            <th scope="col">Grade</th>
            <th scope="col" className="num">
              Paid
            </th>
            <th scope="col" className="num">
              Est. value
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <th scope="row">
                <Link to={`/collection/${item.id}`}>{item.card.name}</Link>
              </th>
              <td>{sportLabel(item.card.sport)}</td>
              <td>{item.card.year}</td>
              <td>{item.card.set_name}</td>
              <td>{item.card.card_number}</td>
              <td>{parallelLine(item) ?? "Base"}</td>
              <td>{item.card.team ?? "—"}</td>
              <td>{formatGrade(item)}</td>
              <td className="num">{formatMoney(item.purchase_price)}</td>
              <td className="num">{formatMoney(item.estimated_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
