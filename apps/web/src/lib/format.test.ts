import { describe, expect, it } from "vitest";
import { makeItem } from "../test/fixtures";
import { formatGrade, formatMoney, parallelLine, setLine, sportLabel } from "./format";

describe("format", () => {
  it("money", () => {
    expect(formatMoney({ amount: "1250.5", currency: "USD" })).toBe("$1,250.50");
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney({ amount: "5", currency: "ZZZ" })).toMatch(/5/);
  });

  it("grades", () => {
    expect(formatGrade({ condition: "graded", grader: "PSA", grade: "10.0" })).toBe("PSA 10");
    expect(formatGrade({ condition: "graded", grader: "BGS", grade: "9.5" })).toBe("BGS 9.5");
    expect(formatGrade({ condition: "raw", grader: null, grade: null })).toBe("Raw");
  });

  it("set and parallel lines", () => {
    const item = makeItem();
    expect(setLine(item)).toBe("2025 Bowman Chrome #CPA-JW");
    expect(parallelLine(item)).toBe("Gold Refractor 12/50");
    expect(parallelLine(makeItem({ serial_number: null }))).toBe("Gold Refractor /50");
    const base = makeItem(
      { serial_number: null },
      { parallel: { id: "b", name: "Base", subset: null, print_run: null, color: null } },
    );
    expect(parallelLine(base)).toBeNull();
    expect(
      parallelLine(
        makeItem(
          { serial_number: 7 },
          { parallel: { id: "b", name: "Base", subset: null, print_run: 99, color: null } },
        ),
      ),
    ).toBe("7/99");
  });

  it("sport labels", () => {
    expect(sportLabel("hockey")).toBe("Hockey");
    expect(sportLabel("curling")).toBe("curling");
  });
});
