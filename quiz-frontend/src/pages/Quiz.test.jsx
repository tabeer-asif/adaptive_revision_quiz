import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Quiz from "./Quiz";

process.env.REACT_APP_API_URL = "http://api.test";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

/** Render Quiz with optional router state (topics) */
function renderQuiz(topics = null) {
  const state = topics ? { topics } : {};
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/quiz", state }]}>
      <Routes>
        <Route path="/quiz" element={<Quiz />} />
        <Route path="/results" element={<div>Results Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

/** Build a minimal MCQ question fixture */
const MCQ_QUESTION = {
  id: "q1",
  type: "MCQ",
  text: "What is 2 + 2?",
  options: { A: "3", B: "4", C: "5" },
};

const MULTI_QUESTION = {
  id: "q2",
  type: "MULTI_MCQ",
  text: "Select all even numbers.",
  options: { A: "2", B: "3", C: "4" },
};

const NUMERIC_QUESTION = {
  id: "q3",
  type: "NUMERIC",
  text: "What is 10 / 2?",
  options: {},
};

const SHORT_QUESTION = {
  id: "q4",
  type: "SHORT",
  text: "Name a primary colour.",
  options: {},
};

/** Mock two-call init sequence: due/count then irt */
function mockInitFetch(dueCount, question) {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: dueCount, total_available: dueCount }) })
    .mockResolvedValueOnce({ ok: true, json: async () => question });
}

describe("Quiz page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
  });

  it("redirects to /login when no token", async () => {
    global.fetch = jest.fn();
    renderQuiz();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/login");
    });
  });

  it("shows loading spinner initially", () => {
    localStorage.setItem("token", "tok");
    global.fetch = jest.fn().mockReturnValue(new Promise(() => {}));
    renderQuiz();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("shows 'No due questions available' when due count is 0", async () => {
    localStorage.setItem("token", "tok");
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ due_count: 0, total_available: 0 }),
    });

    renderQuiz();
    await waitFor(() => {
      expect(screen.getByText("No due questions available")).toBeInTheDocument();
    });
  });

  it("renders an MCQ question with radio options", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, MCQ_QUESTION);

    renderQuiz();
    await waitFor(() => {
      expect(screen.getByText("What is 2 + 2?")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("A: 3")).toBeInTheDocument();
    expect(screen.getByLabelText("B: 4")).toBeInTheDocument();
  });

  it("renders a MULTI_MCQ question with checkboxes", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, MULTI_QUESTION);

    renderQuiz();
    await waitFor(() => {
      expect(screen.getByText("Select all even numbers.")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("A: 2")).toBeInTheDocument();
    expect(screen.getByLabelText("B: 3")).toBeInTheDocument();
  });

  it("renders a NUMERIC question with a number input", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, NUMERIC_QUESTION);

    renderQuiz();
    await waitFor(() => {
      expect(screen.getByText("What is 10 / 2?")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Your answer/i)).toHaveAttribute("type", "number");
  });

  it("renders a SHORT question with a text area", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, SHORT_QUESTION);

    renderQuiz();
    await waitFor(() => {
      expect(screen.getByText("Name a primary colour.")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Your answer/i)).toBeInTheDocument();
  });

  it("renders question image when image_url is present", async () => {
    localStorage.setItem("token", "tok");
    const question = { ...MCQ_QUESTION, image_url: "https://cdn.example/img.png" };
    mockInitFetch(5, question);

    renderQuiz();
    await screen.findByText("What is 2 + 2?");

    const img = screen.getByAltText("Question illustration");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "https://cdn.example/img.png");
  });

  it("does not render image element when image_url is absent", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, MCQ_QUESTION);

    renderQuiz();
    await screen.findByText("What is 2 + 2?");

    expect(screen.queryByAltText("Question illustration")).not.toBeInTheDocument();
  });

  it("Submit button is disabled until an MCQ option is selected", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, MCQ_QUESTION);

    renderQuiz();
    await screen.findByText("What is 2 + 2?");

    expect(screen.getByRole("button", { name: /Submit/i })).toBeDisabled();
    await userEvent.click(screen.getByLabelText("B: 4"));
    expect(screen.getByRole("button", { name: /Submit/i })).not.toBeDisabled();
  });

  it("shows feedback and Next button after submitting a correct MCQ answer", async () => {
    localStorage.setItem("token", "tok");
    mockInitFetch(5, MCQ_QUESTION);
    global.fetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: 5, total_available: 5 }) })  // next due count check
      .mockResolvedValueOnce({ ok: true, json: async () => MCQ_QUESTION });        // next question

    // Re-setup mocks with submit in between
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: 5, total_available: 5 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => MCQ_QUESTION })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ correct: true }) });

    renderQuiz();
    await screen.findByText("What is 2 + 2?"); 

    await userEvent.click(screen.getByLabelText("B: 4"));
    await userEvent.click(screen.getByRole("button", { name: /Submit/i }));

    await waitFor(() => {
      expect(screen.getByText("✅ Correct!")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
  });

  it("shows wrong feedback on incorrect answer", async () => {
    localStorage.setItem("token", "tok");
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: 3, total_available: 3 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => MCQ_QUESTION })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ correct: false }) });

    renderQuiz();
    await screen.findByText("What is 2 + 2?");

    await userEvent.click(screen.getByLabelText("A: 3"));
    await userEvent.click(screen.getByRole("button", { name: /Submit/i }));

    await waitFor(() => {
      expect(screen.getByText("❌ Wrong!")).toBeInTheDocument();
    });
  });

  it("navigates to results when no due questions remain after Next", async () => {
    localStorage.setItem("token", "tok");
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: 1, total_available: 1 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => MCQ_QUESTION })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ correct: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ due_count: 0, total_available: 0 }) }); // no more due

    renderQuiz();
    await screen.findByText("What is 2 + 2?");

    await userEvent.click(screen.getByLabelText("B: 4"));
    await userEvent.click(screen.getByRole("button", { name: /Submit/i }));
    await screen.findByRole("button", { name: /Next/i });
    await userEvent.click(screen.getByRole("button", { name: /Next/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/results",
        expect.objectContaining({ state: expect.objectContaining({ total: 1 }) })
      );
    });
  });
});
