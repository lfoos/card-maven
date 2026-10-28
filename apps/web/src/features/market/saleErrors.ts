import { toFormErrors } from "../../api/fieldErrors";

/** "Sale 2 (price.amount): …" from the API's field errors. */
export function saveError(error: Error): string {
  const { fields, form } = toFormErrors(error);
  const details = Object.entries(fields).map(([loc, message]) => {
    const match = /^sales\.(\d+)\.?(.*)$/.exec(loc);
    if (!match) return `${loc}: ${message}`;
    const where = match[2] ? ` (${match[2]})` : "";
    return `Sale ${Number(match[1]) + 1}${where}: ${message}`;
  });
  return [...details, form].filter(Boolean).join(" ") || "Couldn't save the sales.";
}
