import { describe, expect, it } from "vitest";
import { makeItem } from "../../test/fixtures";
import {
  EMPTY_FORM,
  toNewItem,
  validate,
  valuesFromItem,
  type CardFormValues,
} from "./cardFormModel";

const filled: CardFormValues = {
  ...EMPTY_FORM,
  brand: " Bowman ",
  set_name: "Bowman Chrome",
  card_number: "CPA-JW",
  name: "JJ Wetherholt",
  players: "JJ Wetherholt, , Max Clark ",
  year: "2025",
};

describe("validate", () => {
  it("passes a complete raw card", () => {
    expect(validate(filled)).toEqual({});
  });

  it("requires the identifying fields", () => {
    expect(Object.keys(validate(EMPTY_FORM)).sort()).toEqual([
      "card.brand",
      "card.card_number",
      "card.name",
      "card.set_name",
    ]);
  });

  it.each([
    [{ year: "1700" }, "card.year"],
    [{ year: "abcd" }, "card.year"],
    [{ parallel_name: "Gold", print_run: "0" }, "card.parallel.print_run"],
    [{ serial_number: "0" }, "serial_number"],
    [{ parallel_name: "Gold", print_run: "50", serial_number: "51" }, "serial_number"],
    [{ condition: "graded", grade: "" }, "grade"],
    [{ condition: "graded", grade: "9.3" }, "grade"],
    [{ condition: "graded", grade: "11" }, "grade"],
    [{ purchase_price: "12.345" }, "purchase_price.amount"],
    [{ purchase_price: "-4" }, "purchase_price.amount"],
  ] as const)("%j flags %s", (overrides, field) => {
    expect(validate({ ...filled, ...overrides } as CardFormValues)).toHaveProperty([field]);
  });
});

describe("toNewItem", () => {
  it("trims, splits players, and nulls blanks", () => {
    const body = toNewItem({ ...filled, purchase_price: " 49.99 ", team: "  " });
    expect(body.card).toMatchObject({
      brand: "Bowman",
      year: 2025,
      players: ["JJ Wetherholt", "Max Clark"],
      team: null,
      parallel: null,
    });
    expect(body.purchase_price).toEqual({ amount: "49.99", currency: "USD" });
    expect(body).toMatchObject({
      condition: "raw",
      grader: null,
      grade: null,
      cert_number: null,
      notes: null,
    });
  });

  it("includes grade fields only when graded", () => {
    const graded = toNewItem({
      ...filled,
      condition: "graded",
      grader: "BGS",
      grade: "9.5",
      cert_number: "123",
    });
    expect(graded).toMatchObject({ grader: "BGS", grade: "9.5", cert_number: "123" });
    const raw = toNewItem({
      ...filled,
      condition: "raw",
      grader: "BGS",
      grade: "9.5",
      cert_number: "123",
    });
    expect(raw).toMatchObject({ grader: null, grade: null, cert_number: null });
  });

  it("sends a parallel only when named", () => {
    expect(
      toNewItem({ ...filled, parallel_name: "Refractor", print_run: "499" }).card.parallel,
    ).toEqual({ name: "Refractor", print_run: 499 });
  });
});

describe("valuesFromItem", () => {
  it("round-trips an item into the form", () => {
    const values = valuesFromItem(
      makeItem({ condition: "graded", grader: "PSA", grade: "10.0", cert_number: "9" }),
    );
    expect(values).toMatchObject({
      brand: "bowman",
      players: "JJ Wetherholt",
      parallel_name: "Gold Refractor",
      print_run: "50",
      serial_number: "12",
      purchase_price: "250.00",
      condition: "graded",
      grade: "10.0",
    });
  });

  it("maps base parallels to a blank field", () => {
    const base = makeItem(
      { serial_number: null, purchase_price: null, grader: null },
      {
        parallel: { id: "b", name: "Base", subset: null, print_run: null, color: null },
        team: null,
        subset: null,
      },
    );
    expect(valuesFromItem(base)).toMatchObject({
      parallel_name: "",
      print_run: "",
      serial_number: "",
      purchase_price: "",
      team: "",
      grader: "PSA",
    });
  });
});
