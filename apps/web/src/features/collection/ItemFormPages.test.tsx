import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import { makeItem } from "../../test/fixtures";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { EditItemPage } from "./EditItemPage";
import { NewItemPage } from "./NewItemPage";

const routes = [
  { path: "/collection/new", element: <NewItemPage /> },
  { path: "/collection/:itemId/edit", element: <EditItemPage /> },
  { path: "/collection/:itemId", element: <p>detail page</p> },
  { path: "/collection", element: <p>collection list</p> },
];

describe("NewItemPage", () => {
  it("creates the card and opens it", async () => {
    const { client, request } = fakeClient((_path, options) =>
      options?.method === "POST" ? makeItem({ id: "new-1" }) : { items: [] },
    );
    const { router } = renderWithApi(client, { routes, path: "/collection/new" });
    await userEvent.type(screen.getByLabelText("Brand"), "Topps");
    await userEvent.type(screen.getByLabelText("Set"), "Topps Chrome");
    await userEvent.type(screen.getByLabelText("Card #"), "1");
    await userEvent.type(screen.getByLabelText("Card name"), "Paul Skenes");
    await userEvent.click(screen.getByRole("button", { name: "Add to collection" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collection/new-1"));
    expect(request).toHaveBeenCalledWith(
      "/api/v1/collection/items",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("cancels back to the list", async () => {
    const { client } = fakeClient(() => ({ items: [] }));
    renderWithApi(client, { routes, path: "/collection/new" });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("collection list")).toBeInTheDocument();
  });
});

describe("EditItemPage", () => {
  it("prefills, saves with PATCH, and returns to the card", async () => {
    const { client, request } = fakeClient((_path, options) =>
      options?.method === "PATCH" ? makeItem({ notes: "updated" }) : makeItem(),
    );
    const { router } = renderWithApi(client, { routes, path: "/collection/item-1/edit" });
    expect(await screen.findByLabelText("Set")).toHaveValue("Bowman Chrome");
    await userEvent.type(screen.getByLabelText("Notes"), "updated");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collection/item-1"));
    const patch = request.mock.calls.find(([, o]) => o?.method === "PATCH")!;
    expect(patch[1]!.body).toMatchObject({ notes: "updated", card: { set_name: "Bowman Chrome" } });
  });

  it("explains a load failure", async () => {
    const { client } = fakeClient(() => {
      throw new ApiError(404, "not_found", "Not found");
    });
    renderWithApi(client, { routes, path: "/collection/nope/edit" });
    expect(await screen.findByText("Couldn't load this card.")).toBeInTheDocument();
  });
});
