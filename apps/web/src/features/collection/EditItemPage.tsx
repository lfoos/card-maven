import { Link, useNavigate, useParams } from "react-router";
import { CardForm } from "./CardForm";
import { valuesFromItem } from "./cardFormModel";
import { useItem, useUpdateItem } from "./queries";

export function EditItemPage() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const query = useItem(itemId);
  const update = useUpdateItem(itemId);

  if (query.isPending) return <p className="muted">Loading…</p>;
  if (query.isError) {
    return (
      <div role="alert" className="notice notice--error">
        <p>Couldn't load this card.</p>
        <Link to="/collection">Back to collection</Link>
      </div>
    );
  }
  return (
    <section className="page">
      <h1>Edit {query.data.card.name}</h1>
      <CardForm
        initial={valuesFromItem(query.data)}
        submitLabel="Save changes"
        onCancel={() => void navigate(`/collection/${itemId}`)}
        onSubmit={async (body) => {
          // The form edits everything, so send the whole card and holding.
          await update.mutateAsync(body);
          void navigate(`/collection/${itemId}`);
        }}
      />
    </section>
  );
}
