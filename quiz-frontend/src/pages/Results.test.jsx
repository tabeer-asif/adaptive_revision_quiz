import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Results from "./Results";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderResults(state = {}) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/results", state }]}>
      <Results />
    </MemoryRouter>
  );
}

describe("Results page", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders heading and default score when no state provided", () => {
    renderResults();
    expect(screen.getByText(/Results/i)).toBeInTheDocument();
    expect(screen.getByText(/You scored 0 out of 1/i)).toBeInTheDocument();
    expect(screen.getByText(/0% Accuracy/i)).toBeInTheDocument();
  });

  it("renders correct score and percentage", () => {
    renderResults({ score: 7, total: 10 });
    expect(screen.getByText(/You scored 7 out of 10/i)).toBeInTheDocument();
    expect(screen.getByText(/70% Accuracy/i)).toBeInTheDocument();
  });

  it("shows high score message when percentage >= 80", () => {
    renderResults({ score: 9, total: 10 });
    expect(screen.getByText(/Great job/i)).toBeInTheDocument();
  });

  it("shows medium score message when percentage is 50-79", () => {
    renderResults({ score: 6, total: 10 });
    expect(screen.getByText(/Keep practicing/i)).toBeInTheDocument();
  });

  it("shows low score message when percentage < 50", () => {
    renderResults({ score: 3, total: 10 });
    expect(screen.getByText(/more review/i)).toBeInTheDocument();
  });

  it("navigates to /quiz when Try Again is clicked", async () => {
    renderResults({ score: 5, total: 10 });
    await userEvent.click(screen.getByRole("button", { name: /Try Again/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/quiz");
  });

  it("navigates to /home when Back to Home is clicked", async () => {
    renderResults({ score: 5, total: 10 });
    await userEvent.click(screen.getByRole("button", { name: /Back to Home/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/home");
  });
});
