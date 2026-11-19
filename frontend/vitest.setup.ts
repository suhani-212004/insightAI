import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer needs ResizeObserver in jsdom.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as any).ResizeObserver = RO;
