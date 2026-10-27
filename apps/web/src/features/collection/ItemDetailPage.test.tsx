import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import { makeItem } from "../../test/fixtures";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { ItemDetailPage } from "./ItemDetailPage";

const routes = [
  { path: "/collection/:itemId", element: <ItemDetailPage /> },
  { path: "/collection", element: <p>collection list</p> },
];

describe("ItemDetailPage", () => {
  it("shows the card's facts", async () => {
    const item = makeItem(
      { condition: "graded", grader: "PSA", grade: "10.0", cert_number: "777", notes: "case hit" },
      { is_rookie: true },
    );
    const { client } = fakeClient(() => item);
    renderWithApi(client, { routes, path: "/collection/item-1" });
    expect(await screen.findByRole("heading", { name: "JJ Wetherholt" })).toBeInTheDocument();
    expect(screen.getByText("PSA 10 · cert 777")).toBeInTheDocument();
    expect(screen.getByText("Gold Refractor 12/50")).toBeInTheDocument();
    expect(screen.getByText("case hit")).toBeInTheDocument();
    expect(screen.getByText("Rookie")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute(
      "href",
      "/collection/item-1/edit",
    );
  });

  it("confirms before deleting, then returns to the list", async () => {
    const { client, request } = fakeClient((_path, options) =>
      options?.method === "DELETE" ? undefined : makeItem(),
    );
    renderWithApi(client, { routes, path: "/collection/item-1" });
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/can't be undone/);
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete card" }));
    expect(await screen.findByText("collection list")).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith("/api/v1/collection/items/item-1", { method: "DELETE" });
  });

  it("reports a failed delete", async () => {
    const { client } = fakeClient((_path, options) => {
      if (options?.method === "DELETE")
        throw new ApiError(503, "dependency_unavailable", "Dependency unavailable");
      return makeItem();
    });
    renderWithApi(client, { routes, path: "/collection/item-1" });
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete card" }));
    expect(await screen.findByText(/couldn't delete/i)).toBeInTheDocument();
  });

  it.each([
    [new ApiError(404, "not_found", "Not found"), "That card isn't in your collection."],
    [new ApiError(500, "internal_error", "Oops"), "Couldn't load this card."],
  ])("explains load failures", async (error, message) => {
    const { client } = fakeClient(() => {
      throw error;
    });
    renderWithApi(client, { routes, path: "/collection/missing" });
    expect(await screen.findByText(message)).toBeInTheDocument();
  });
});
