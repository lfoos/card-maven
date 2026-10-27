import { describe, expect, it } from "vitest";
import { isProblem } from "./errors";

describe("isProblem", () => {
  it.each([
    [{ status: 404, code: "not_found", title: "Not found" }, true],
    [{ status: "404", code: "not_found" }, false],
    [{ status: 404 }, false],
    [null, false],
    ["error", false],
  ])("%j -> %s", (value, expected) => {
    expect(isProblem(value)).toBe(expected);
  });
});
