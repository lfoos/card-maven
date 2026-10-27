import { ApiError } from "./errors";
import type { FieldError } from "./types";

export interface FormErrors {
  /** Keyed by dotted field path, e.g. "card.year". */
  fields: Record<string, string>;
  /** Errors that aren't about one field (and anything unexpected). */
  form: string | null;
}

export const NO_ERRORS: FormErrors = { fields: {}, form: null };

/** Turn an API failure into messages a form can place next to its inputs. */
export function toFormErrors(error: unknown): FormErrors {
  if (!(error instanceof ApiError))
    return { fields: {}, form: "Something went wrong. Please try again." };
  if (error.isNetworkError) return { fields: {}, form: error.message };
  const list = (error.problem?.errors as FieldError[] | undefined) ?? [];
  const fields: Record<string, string> = {};
  const general: string[] = [];
  for (const { loc, message } of list) {
    if (!loc || loc === "body") general.push(message);
    else fields[loc] ??= message;
  }
  if (list.length === 0) general.push(error.detail ?? error.message);
  return { fields, form: general.length ? general.join(" ") : null };
}
