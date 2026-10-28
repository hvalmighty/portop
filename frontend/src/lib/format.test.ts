import { describe, expect, it } from "vitest";
import { money, pct, tone } from "./format";

describe("format", () => {
  it("compacts money like the trading terminal", () => {
    expect(money(445_690_000, "SGD")).toBe("SGD 445.69m");
    expect(money(-6_700, "SGD")).toBe("-SGD 6.7k");
    expect(money(1_200_000)).toBe("1.20m");
    expect(money(null)).toBe("—");
  });
  it("formats percentages and tones", () => {
    expect(pct(0.284, 2, true)).toBe("+0.28%");
    expect(tone(-1)).toBe("text-down");
    expect(tone(0)).toBe("text-dim");
  });
});
