import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { CardForm } from "./CardForm";
import { EMPTY_FORM } from "./cardFormModel";

function setup(onSubmit = vi.fn((_body: unknown) => Promise.resolve())) {
  const { client, request } = fakeClient((path) => {
    if (path.startsWith("/api/v1/catalog/sets")) {
      return {
        items: [
          { id: "s1", sport: "baseball", brand: "bowman", year: 2025, name: "Bowman Chrome" },
        ],
      };
    }
    if (path.startsWith("/api/v1/catalog/players"))
      return { items: [{ id: "p1", sport: "baseball", full_name: "JJ Wetherholt" }] };
    return {};
  });
  renderWithApi(client, {
    element: <CardForm initial={EMPTY_FORM} submitLabel="Add" onSubmit={onSubmit} />,
  });
  return { onSubmit, request };
}

async function fillRequired() {
  await userEvent.type(screen.getByLabelText("Brand"), "Bowman");
  await userEvent.type(screen.getByLabelText("Set"), "Bowman Chrome");
  await userEvent.type(screen.getByLabelText("Card #"), "CPA-JW");
  await userEvent.type(screen.getByLabelText("Card name"), "JJ Wetherholt");
}

describe("CardForm", () => {
  it("blocks submission and marks invalid fields", async () => {
    const { onSubmit } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/fix the highlighted/i);
    expect(screen.getByLabelText("Brand")).toHaveAttribute("aria-invalid", "true");
  });

  it("submits a well-formed body", async () => {
    const { onSubmit } = setup();
    await fillRequired();
    await userEvent.type(screen.getByLabelText("Price paid (USD)"), "250");
    await userEvent.click(screen.getByLabelText("Autograph"));
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({
      card: {
        brand: "Bowman",
        set_name: "Bowman Chrome",
        card_number: "CPA-JW",
        is_autograph: true,
        sport: "baseball",
      },
      purchase_price: { amount: "250", currency: "USD" },
    });
  });

  it("shows grade fields only for graded cards", async () => {
    setup();
    expect(screen.queryByLabelText("Grade")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Condition"), "graded");
    expect(screen.getByLabelText("Grade")).toBeInTheDocument();
    expect(screen.getByLabelText("Grader")).toHaveValue("PSA");
  });

  it("disables print run until a parallel is named", async () => {
    setup();
    expect(screen.getByLabelText("Print run")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Parallel"), "Gold");
    expect(screen.getByLabelText("Print run")).toBeEnabled();
  });

  it("maps server validation errors onto fields", async () => {
    const failure = new ApiError(422, "invalid_input", "Invalid input", {
      title: "Invalid input",
      status: 422,
      code: "invalid_input",
      detail: "unknown sport",
      errors: [{ loc: "card.sport", message: "unknown sport 'curling'" }],
    });
    setup(vi.fn((_body: unknown) => Promise.reject(failure)));
    await fillRequired();
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("unknown sport 'curling'")).toBeInTheDocument();
    expect(screen.getByLabelText("Sport")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Add" })).toBeEnabled();
  });

  it("suggests sets and players from the catalog", async () => {
    const { request } = setup();
    await userEvent.type(screen.getByLabelText("Set"), "chr");
    await waitFor(() =>
      expect(request.mock.calls.some(([p]) => p.startsWith("/api/v1/catalog/sets?q=chr"))).toBe(
        true,
      ),
    );
    await userEvent.type(screen.getByLabelText("Players"), "Max Clark, wet");
    await waitFor(() =>
      expect(request.mock.calls.some(([p]) => p.startsWith("/api/v1/catalog/players?q=wet"))).toBe(
        true,
      ),
    );
    await waitFor(() =>
      expect(document.querySelector('option[value="JJ Wetherholt"]')).not.toBeNull(),
    );
  });

  it("calls cancel", async () => {
    const onCancel = vi.fn();
    const { client } = fakeClient(() => ({ items: [] }));
    renderWithApi(client, {
      element: (
        <CardForm initial={EMPTY_FORM} submitLabel="Add" onSubmit={vi.fn()} onCancel={onCancel} />
      ),
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
