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

const SOURCES: Record<string, string> = {
  manual: "You",
  fixture: "Sample data",
  ebay_browse: "eBay",
};

export function sourceLabel(code: string): string {
  return SOURCES[code] ?? code;
}

/** "Oct 27, 2026". Dates from the API are UTC. */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(
    new Date(iso),
  );
}

/** "just now", "12 min ago", "3 h ago", "2 days ago". */
export function formatAge(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
