import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { makeItem } from "../../test/fixtures";
import { CollectionPage } from "./CollectionPage";

const routes = [{ path: "/collection", element: <CollectionPage /> }];

describe("CollectionPage", () => {
  it("shows cards in a grid, then a table", async () => {
    const { client } = fakeClient(() => ({ items: [makeItem()], next_cursor: null }));
    renderWithApi(client, { routes, path: "/collection" });
    expect(await screen.findByText("JJ Wetherholt")).toBeInTheDocument();
    expect(screen.getByText("Gold Refractor 12/50")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "$250.00" })).toBeInTheDocument();
  });

  it("pages with Load more", async () => {
    const { client, request } = fakeClient((path) =>
      path.includes("cursor=")
        ? { items: [makeItem({ id: "item-2" }, { name: "Max Clark" })], next_cursor: null }
        : { items: [makeItem()], next_cursor: "next" },
    );
    renderWithApi(client, { routes, path: "/collection" });
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Max Clark")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(request.mock.calls.at(-1)![0]).toContain("cursor=next");
  });

  it("puts filters in the URL and the request", async () => {
    const { client, request } = fakeClient(() => ({ items: [], next_cursor: null }));
    const { router } = renderWithApi(client, { routes, path: "/collection" });
    await userEvent.selectOptions(await screen.findByLabelText("Sport"), "hockey");
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "name");
    await userEvent.type(screen.getByLabelText("Search your cards"), "young guns");
    await waitFor(() => expect(router.state.location.search).toContain("q=young+guns"));
    expect(router.state.location.search).toContain("sport=hockey");
    await waitFor(() => expect(request.mock.calls.at(-1)![0]).toContain("q=young+guns"));
    expect(request.mock.calls.at(-1)![0]).toContain("sort=name");
    expect(await screen.findByText("No cards match these filters.")).toBeInTheDocument();
  });

  it("reads filters from the URL", async () => {
    const { client, request } = fakeClient(() => ({ items: [], next_cursor: null }));
    renderWithApi(client, { routes, path: "/collection?year=2024&condition=graded&sort=bogus" });
    await waitFor(() => expect(request).toHaveBeenCalled());
    const path = request.mock.calls[0]![0];
    expect(path).toContain("year=2024");
    expect(path).toContain("condition=graded");
    expect(path).not.toContain("bogus");
  });

  it("invites the first card when empty", async () => {
    const { client } = fakeClient(() => ({ items: [], next_cursor: null }));
    renderWithApi(client, { routes, path: "/collection" });
    expect(await screen.findByRole("link", { name: "Add your first card" })).toHaveAttribute(
      "href",
      "/collection/new",
    );
  });

  it("offers a retry on failure", async () => {
    let fail = true;
    const { client } = fakeClient(() => {
      if (fail) throw new Error("down");
      return { items: [makeItem()], next_cursor: null };
    });
    renderWithApi(client, { routes, path: "/collection" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load/i);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("JJ Wetherholt")).toBeInTheDocument();
  });

  it("year filter applies on blur and ignores junk", async () => {
    const { client } = fakeClient(() => ({ items: [], next_cursor: null }));
    const { router } = renderWithApi(client, { routes, path: "/collection" });
    const year = await screen.findByLabelText("Year");
    await userEvent.type(year, "20");
    await userEvent.tab();
    expect(router.state.location.search).not.toContain("year=");
    await userEvent.type(year, "25");
    await userEvent.tab();
    expect(router.state.location.search).toContain("year=2025");
  });
});
