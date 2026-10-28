import type { Grader, ManualSale, SaleType } from "../../api/types";

/** Most sales a single request accepts (the API's limit). */
export const MAX_SALES = 200;
/** 200 rows is a few KB; anything this big isn't a sales export. */
export const MAX_CSV_BYTES = 1_000_000;

const GRADERS: readonly Grader[] = ["PSA", "BGS", "SGC", "CGC", "TAG"];
const SALE_TYPES: readonly SaleType[] = ["auction", "fixed_price", "best_offer", "other"];
const HEADER_ALIASES: Record<string, string> = {
  date: "sold_on",
  sold: "sold_on",
  sold_on: "sold_on",
  sale_date: "sold_on",
  price: "price",
  amount: "price",
  sold_price: "price",
  currency: "currency",
  grader: "grader",
  grade: "grade",
  title: "title",
  url: "url",
  link: "url",
  type: "sale_type",
  sale_type: "sale_type",
};

export interface CsvResult {
  sales: ManualSale[];
  /** Human-readable problems, with 1-based line numbers. */
  errors: string[];
}

/** Split CSV text into rows. Handles quoted fields, escaped quotes, and CRLF. */
export function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((cell) => cell.trim() !== ""));
}

function normalizeDate(value: string): string | null {
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(value);
  const us = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value);
  const [y, m, d] = iso
    ? [iso[1], iso[2], iso[3]]
    : us
      ? [us[3], us[1], us[2]]
      : [undefined, undefined, undefined];
  if (!y || !m || !d) return null;
  const date = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  if (date.getUTCMonth() !== Number(m) - 1 || date.getUTCDate() !== Number(d)) return null;
  return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
}

function normalizePrice(value: string): string | null {
  const cleaned = value.replace(/[$,\s]/g, "");
  return /^\d+(\.\d{1,2})?$/.test(cleaned) ? cleaned : null;
}

/**
 * Parse sales from CSV. The first row is a header; columns are matched by
 * name (date, price, and optionally currency, grader, grade, title, url,
 * type). A row with a grader and grade is a graded sale; otherwise raw.
 */
export function parseSalesCsv(text: string): CsvResult {
  const [first, ...body] = csvRows(text);
  if (!first) return { sales: [], errors: ["The file is empty."] };
  const header = first.map((h) => HEADER_ALIASES[h.trim().toLowerCase().replace(/\s+/g, "_")]);
  if (!header.includes("sold_on") || !header.includes("price")) {
    return {
      sales: [],
      errors: ["The first row must name the columns, including date and price."],
    };
  }
  const sales: ManualSale[] = [];
  const errors: string[] = [];
  body.forEach((cells, index) => {
    const line = index + 2;
    const value = (key: string) => {
      const at = header.indexOf(key);
      return at >= 0 ? (cells[at] ?? "").trim() : "";
    };
    const soldOn = normalizeDate(value("sold_on"));
    const price = normalizePrice(value("price"));
    if (!soldOn) return errors.push(`Line ${line}: "${value("sold_on")}" isn't a date.`);
    if (!price) return errors.push(`Line ${line}: "${value("price")}" isn't a price.`);
    const graderText = value("grader").toUpperCase();
    const grader = GRADERS.find((g) => g === graderText);
    const grade = value("grade");
    if (graderText && !grader) return errors.push(`Line ${line}: unknown grader "${graderText}".`);
    if (Boolean(grader) !== Boolean(grade)) {
      return errors.push(`Line ${line}: a graded sale needs both a grader and a grade.`);
    }
    const saleType = SALE_TYPES.find((t) => t === value("sale_type").toLowerCase());
    const sale: ManualSale = {
      sold_on: soldOn,
      price: { amount: price, currency: value("currency").toUpperCase() || "USD" },
      condition: grader ? "graded" : "raw",
    };
    if (grader) Object.assign(sale, { grader, grade });
    if (value("title")) sale.title = value("title");
    if (value("url")) sale.url = value("url");
    if (saleType) sale.sale_type = saleType;
    sales.push(sale);
  });
  if (sales.length > MAX_SALES) {
    errors.push(`Up to ${MAX_SALES} sales at a time; this file has ${sales.length}.`);
  }
  return { sales, errors };
}
