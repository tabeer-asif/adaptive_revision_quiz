import { render } from "@testing-library/react";
import MathText from "./MathText";

describe("MathText", () => {
  it("renders explicit delimiters", () => {
    const { container } = render(<MathText text={"Inline \\(x+1\\) and block \\[y=mx+b\\]"} />);
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
  });

  it("keeps currency-like dollar values as plain text", () => {
    const { getByText } = render(<MathText text={"This costs $20$ today."} />);
    expect(getByText("This costs $20$ today.")).toBeInTheDocument();
  });

  it("keeps legacy dollar-delimited content as plain text", () => {
    const { container, getByText } = render(<MathText text={"Solve $x+1$ now"} />);
    expect(getByText("Solve $x+1$ now")).toBeInTheDocument();
    expect(container.querySelector(".katex")).toBeNull();
  });
});
