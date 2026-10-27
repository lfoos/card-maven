import type { Item, Money } from "../api/types";

const SPORTS: Record<string, string> = {
  baseball: "Baseball",
  basketball: "Basketball",
  football: "Football",
  hockey: "Hockey",
};

export const SPORT_OPTIONS = Object.entries(SPORTS).map(([value, label]) => ({ value, label }));

export function sportLabel(code: string): string {
  return SPORTS[code] ?? code;
}

export function formatMoney(money: Money | null | undefined): string {
  if (!money) return "—";
  const amount = Number(money.amount);
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: money.currency }).format(
      amount,
    );
  } catch {
    return `${money.amount} ${money.currency}`;
  }
}

/** "PSA 10", "BGS 9.5", or "Raw". */
export function formatGrade(item: Pick<Item, "condition" | "grader" | "grade">): string {
  if (item.condition !== "graded" || !item.grader || !item.grade) return "Raw";
  const grade = item.grade.endsWith(".0") ? item.grade.slice(0, -2) : item.grade;
  return `${item.grader} ${grade}`;
}

/** "2025 Bowman Chrome #CPA-JW". */
export function setLine(item: Item): string {
  const { year, set_name, card_number } = item.card;
  return `${year} ${set_name} #${card_number}`;
}

/** "Gold Refractor 12/50", or null for base cards without a serial. */
export function parallelLine(item: Item): string | null {
  const { parallel } = item.card;
  const isBase = parallel.name.toLowerCase() === "base";
  const run = parallel.print_run ? `/${parallel.print_run}` : "";
  const serial = item.serial_number ? `${item.serial_number}${run}` : run;
  if (isBase && !serial) return null;
  return [isBase ? "" : parallel.name, serial].filter(Boolean).join(" ");
}
