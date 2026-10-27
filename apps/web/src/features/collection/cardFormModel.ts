import type { Condition, Item, NewItem } from "../../api/types";

/** Every input in the card form, as strings (what HTML inputs hold). */
export interface CardFormValues {
  sport: string;
  year: string;
  brand: string;
  set_name: string;
  card_number: string;
  name: string;
  players: string;
  team: string;
  subset: string;
  parallel_name: string;
  print_run: string;
  is_rookie: boolean;
  is_autograph: boolean;
  is_memorabilia: boolean;
  condition: Condition;
  grader: string;
  grade: string;
  cert_number: string;
  serial_number: string;
  purchase_price: string;
  acquired_on: string;
  notes: string;
}

export const EMPTY_FORM: CardFormValues = {
  sport: "baseball",
  year: String(new Date().getFullYear()),
  brand: "",
  set_name: "",
  card_number: "",
  name: "",
  players: "",
  team: "",
  subset: "",
  parallel_name: "",
  print_run: "",
  is_rookie: false,
  is_autograph: false,
  is_memorabilia: false,
  condition: "raw",
  grader: "PSA",
  grade: "",
  cert_number: "",
  serial_number: "",
  purchase_price: "",
  acquired_on: "",
  notes: "",
};

export const GRADERS = ["PSA", "BGS", "SGC", "CGC", "TAG"] as const;

export function valuesFromItem(item: Item): CardFormValues {
  const { card } = item;
  const isBase = card.parallel.name.toLowerCase() === "base";
  return {
    sport: card.sport,
    year: String(card.year),
    brand: card.brand,
    set_name: card.set_name,
    card_number: card.card_number,
    name: card.name,
    players: card.players.join(", "),
    team: card.team ?? "",
    subset: card.subset ?? "",
    parallel_name: isBase ? "" : card.parallel.name,
    print_run: card.parallel.print_run ? String(card.parallel.print_run) : "",
    is_rookie: card.is_rookie,
    is_autograph: card.is_autograph,
    is_memorabilia: card.is_memorabilia,
    condition: item.condition as Condition,
    grader: item.grader ?? "PSA",
    grade: item.grade ?? "",
    cert_number: item.cert_number ?? "",
    serial_number: item.serial_number ? String(item.serial_number) : "",
    purchase_price: item.purchase_price?.amount ?? "",
    acquired_on: item.acquired_on ?? "",
    notes: item.notes ?? "",
  };
}

const blank = (value: string) => value.trim() === "";
const orNull = (value: string) => (blank(value) ? null : value.trim());
const intOrNull = (value: string) => (blank(value) ? null : Number.parseInt(value, 10));

/** Checks that need no server round-trip. Field keys match the API's `loc`s. */
export function validate(values: CardFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  const required: [keyof CardFormValues, string][] = [
    ["brand", "card.brand"],
    ["set_name", "card.set_name"],
    ["card_number", "card.card_number"],
    ["name", "card.name"],
  ];
  for (const [field, loc] of required) {
    if (blank(values[field] as string)) errors[loc] = "Required";
  }
  const year = Number(values.year);
  if (!Number.isInteger(year) || year < 1860 || year > 2100)
    errors["card.year"] = "Enter a year between 1860 and 2100";
  if (!blank(values.print_run) && !(Number(values.print_run) >= 1))
    errors["card.parallel.print_run"] = "Must be 1 or more";
  if (!blank(values.serial_number) && !(Number(values.serial_number) >= 1))
    errors["serial_number"] = "Must be 1 or more";
  if (
    !blank(values.serial_number) &&
    !blank(values.print_run) &&
    Number(values.serial_number) > Number(values.print_run)
  ) {
    errors["serial_number"] = `Can't exceed the print run of /${values.print_run}`;
  }
  if (values.condition === "graded") {
    const grade = Number(values.grade);
    if (blank(values.grade) || !(grade >= 1 && grade <= 10) || (grade * 2) % 1 !== 0) {
      errors["grade"] = "Enter a grade from 1 to 10 in steps of 0.5";
    }
  }
  if (!blank(values.purchase_price) && !/^\d+(\.\d{1,2})?$/.test(values.purchase_price.trim())) {
    errors["purchase_price.amount"] = "Enter an amount like 49.99";
  }
  return errors;
}

/** Build the API request body. Text is trimmed; blanks become null. */
export function toNewItem(values: CardFormValues): NewItem {
  const graded = values.condition === "graded";
  const parallelName = values.parallel_name.trim();
  return {
    card: {
      sport: values.sport,
      brand: values.brand.trim(),
      year: Number(values.year),
      set_name: values.set_name.trim(),
      card_number: values.card_number.trim(),
      name: values.name.trim(),
      players: values.players
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean),
      team: orNull(values.team),
      subset: orNull(values.subset),
      parallel: parallelName
        ? { name: parallelName, print_run: intOrNull(values.print_run) }
        : null,
      is_rookie: values.is_rookie,
      is_autograph: values.is_autograph,
      is_memorabilia: values.is_memorabilia,
    },
    condition: values.condition,
    grader: graded ? (values.grader as (typeof GRADERS)[number]) : null,
    grade: graded ? values.grade.trim() : null,
    cert_number: graded ? orNull(values.cert_number) : null,
    serial_number: intOrNull(values.serial_number),
    purchase_price: blank(values.purchase_price)
      ? null
      : { amount: values.purchase_price.trim(), currency: "USD" },
    acquired_on: orNull(values.acquired_on),
    notes: orNull(values.notes),
  };
}
