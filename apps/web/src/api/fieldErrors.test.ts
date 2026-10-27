import { describe, expect, it } from "vitest";
import { ApiError } from "./errors";
import { toFormErrors } from "./fieldErrors";

const problem = (errors: { loc: string; message: string }[], detail = "Invalid input") =>
  new ApiError(422, "invalid_input", "Invalid input", {
    title: "Invalid input",
    status: 422,
    code: "invalid_input",
    detail,
    errors,
  });

describe("toFormErrors", () => {
  it("places field errors and keeps the first per field", () => {
    const result = toFormErrors(
      problem([
        { loc: "card.year", message: "too old" },
        { loc: "card.year", message: "second" },
        { loc: "body", message: "graded cards need a grader and a grade" },
      ]),
    );
    expect(result).toEqual({
      fields: { "card.year": "too old" },
      form: "graded cards need a grader and a grade",
    });
  });

  it("falls back to the problem detail", () => {
    expect(
      toFormErrors(
        new ApiError(409, "conflict", "Conflict", {
          title: "Conflict",
          status: 409,
          code: "conflict",
          detail: "busy",
        }),
      ),
    ).toEqual({
      fields: {},
      form: "busy",
    });
  });

  it("handles network and unknown errors", () => {
    expect(
      toFormErrors(new ApiError(0, "network_error", "Could not reach the Card Maven API")).form,
    ).toMatch(/reach/);
    expect(toFormErrors(new Error("boom")).form).toMatch(/something went wrong/i);
  });
});
