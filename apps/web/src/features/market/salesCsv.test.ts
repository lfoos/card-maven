import { describe, expect, it } from "vitest";
import { MAX_SALES, csvRows, parseSalesCsv } from "./salesCsv";

describe("csvRows", () => {
  it("handles quotes, escaped quotes, CRLF, and blank lines", () => {
    expect(csvRows('a,b\r\n"x, y","say ""hi"""\n\n1,2')).toEqual([
      ["a", "b"],
      ["x, y", 'say "hi"'],
      ["1", "2"],
    ]);
  });

  it("keeps a last line without a newline and empty trailing cells", () => {
    expect(csvRows("a,b\n1,")).toEqual([
      ["a", "b"],
      ["1", ""],
    ]);
  });
});

describe("parseSalesCsv", () => {
  it("maps columns by name, in any order, with aliases", () => {
    const result = parseSalesCsv(
      'Price,Sale Date,Grader,Grade,Title,Link,Type\n"$1,095.50",10/3/2026,psa,10,Big one,https://e.x/1,auction\n12,2026-09-30,,,,,',
    );
    expect(result.errors).toEqual([]);
    expect(result.sales).toEqual([
      {
        sold_on: "2026-10-03",
        price: { amount: "1095.50", currency: "USD" },
        condition: "graded",
        grader: "PSA",
        grade: "10",
        title: "Big one",
        url: "https://e.x/1",
        sale_type: "auction",
      },
      { sold_on: "2026-09-30", price: { amount: "12", currency: "USD" }, condition: "raw" },
    ]);
  });

  it("reports bad rows with line numbers and keeps good ones", () => {
    const result = parseSalesCsv(
      "date,price,grader,grade,currency\n2026-02-30,5,,,\n2026-01-01,abc,,,\n2026-01-01,5,XYZ,9,\n2026-01-01,5,PSA,,\n2026-01-01,5,,,cad",
    );
    expect(result.errors).toEqual([
      'Line 2: "2026-02-30" isn\'t a date.',
      'Line 3: "abc" isn\'t a price.',
      'Line 4: unknown grader "XYZ".',
      "Line 5: a graded sale needs both a grader and a grade.",
    ]);
    expect(result.sales).toEqual([
      { sold_on: "2026-01-01", price: { amount: "5", currency: "CAD" }, condition: "raw" },
    ]);
  });

  it.each([
    ["", "The file is empty."],
    ["title,url\nx,y", "The first row must name the columns, including date and price."],
  ])("rejects files without the required columns: %j", (text, error) => {
    expect(parseSalesCsv(text)).toEqual({ sales: [], errors: [error] });
  });

  it("enforces the per-request limit", () => {
    const rows = Array.from({ length: MAX_SALES + 1 }, () => "2026-01-01,1").join("\n");
    const result = parseSalesCsv(`date,price\n${rows}`);
    expect(result.errors).toEqual([`Up to ${MAX_SALES} sales at a time; this file has 201.`]);
  });
});
