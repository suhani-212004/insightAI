import { render, screen } from "@testing-library/react";
import { ChartRenderer } from "@/components/charts/ChartRenderer";
import type { ChartType } from "@/lib/types";

const rows = [
  { region: "North", category: "A", revenue: 100 },
  { region: "South", category: "B", revenue: 50 },
];
const columns = ["region", "category", "revenue"];

describe("ChartRenderer", () => {
  it.each<ChartType>(["line", "bar", "pie", "scatter", "funnel"])("renders a %s chart container", (type) => {
    render(<ChartRenderer spec={{ type, x: "region", y: ["revenue"] }} columns={columns} rows={rows} />);
    expect(screen.getByTestId(`chart-${type}`)).toBeInTheDocument();
  });

  it("renders a heatmap grid with values", () => {
    render(<ChartRenderer spec={{ type: "heatmap", x: "region", y: ["category"], value: "revenue" }} columns={columns} rows={rows} />);
    expect(screen.getByTestId("chart-heatmap")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("falls back to a table", () => {
    render(<ChartRenderer spec={{ type: "table", y: [] }} columns={columns} rows={rows} />);
    expect(screen.getByText("North")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<ChartRenderer spec={{ type: "bar", y: [] }} columns={columns} rows={[]} />);
    expect(screen.getByText("No rows returned.")).toBeInTheDocument();
  });
});
