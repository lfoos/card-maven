import { useNavigate } from "react-router";
import { CardForm } from "./CardForm";
import { EMPTY_FORM } from "./cardFormModel";
import { useCreateItem } from "./queries";

export function NewItemPage() {
  const navigate = useNavigate();
  const create = useCreateItem();
  return (
    <section className="page">
      <h1>Add a card</h1>
      <CardForm
        initial={EMPTY_FORM}
        submitLabel="Add to collection"
        onCancel={() => void navigate("/collection")}
        onSubmit={async (body) => {
          const item = await create.mutateAsync(body);
          void navigate(`/collection/${item.id}`);
        }}
      />
    </section>
  );
}
