import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import { saveError } from "./saleErrors";

function invalid(errors: { loc: string; message: string }[]) {
  return new ApiError(422, "invalid_input", "Invalid input", {
    title: "Invalid input",
    status: 422,
    code: "invalid_input",
    errors,
  });
}

describe("saveError", () => {
  it("names the sale and field", () => {
    expect(
      saveError(
        invalid([
          { loc: "sales.1.price.amount", message: "must be positive" },
          { loc: "sales.0", message: "a graded sale needs a grade" },
          { loc: "other", message: "odd" },
        ]),
      ),
    ).toBe(
      "Sale 2 (price.amount): must be positive Sale 1: a graded sale needs a grade other: odd",
    );
  });

  it("falls back to a general message", () => {
    expect(saveError(new Error("boom"))).toBe("Something went wrong. Please try again.");
    expect(saveError(invalid([{ loc: "body", message: "too many" }]))).toBe("too many");
  });
});
