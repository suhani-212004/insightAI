import { formatLabel, formatNumber, heatColor, resolveAxes, toCSV, toFunnel, toHeatmap } from "@/lib/chartData";

describe("chartData helpers", () => {
  it("formats numbers compactly", () => {
    expect(formatNumber(1234)).toBe("1,234");
    expect(formatNumber(12345)).toBe("12.3K");
    expect(formatNumber(2_500_000)).toBe("2.5M");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatNumber(null)).toBe("");
    expect(formatNumber("x")).toBe("x");
  });

  it("shortens midnight timestamps", () => {
    expect(formatLabel("2026-01-01T00:00:00")).toBe("2026-01-01");
    expect(formatLabel("North")).toBe("North");
  });

  it("resolves axes when the spec is wrong", () => {
    const rows = [{ month: "2026-01", revenue: 10, units: 2 }];
    expect(resolveAxes({ type: "bar", x: "nope", y: ["bad"] }, ["month", "revenue", "units"], rows))
      .toEqual({ x: "month", y: ["revenue", "units"] });
    expect(resolveAxes({ type: "bar", x: "month", y: ["units"] }, ["month", "revenue", "units"], rows))
      .toEqual({ x: "month", y: ["units"] });
  });

  it("uses a numeric x axis for scatter plots", () => {
    const rows = [{ product: "A", price: 10, qty: 3 }];
    expect(resolveAxes({ type: "scatter", y: [] }, ["product", "price", "qty"], rows))
      .toEqual({ x: "price", y: ["qty"] });
  });

  it("builds heatmap cells", () => {
    const h = toHeatmap([{ r: "N", c: "A", v: 1 }, { r: "N", c: "B", v: 5 }, { r: "S", c: "A", v: 3 }], "r", "c", "v");
    expect(h.xs).toEqual(["N", "S"]);
    expect(h.ys).toEqual(["A", "B"]);
    expect(h.min).toBe(1);
    expect(h.max).toBe(5);
    expect(h.cells.get("N\u0000B")).toBe(5);
    expect(heatColor(0)).toContain("95%");
    expect(heatColor(2)).toBe(heatColor(1));
  });

  it("builds funnel data and CSV", () => {
    expect(toFunnel([{ s: "Visits", v: 10 }], "s", "v")[0]).toMatchObject({ name: "Visits", value: 10 });
    expect(toCSV(["a", "b"], [{ a: "x,y", b: 'say "hi"' }, { a: null, b: 2 }])).toBe('a,b\n"x,y","say ""hi"""\n,2');
  });
});
