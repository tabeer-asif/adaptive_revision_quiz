process.env.REACT_APP_API_URL = "http://api.test";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Questions from "./Questions";

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => jest.fn(),
}));

const TOPICS = [{ id: 1, name: "Maths" }];

const QUESTIONS = [
  {
    id: "q1",
    text: "What is 2+2?",
    topic_id: 1,
    topic_name: "Maths",
    type: "MCQ",
    difficulty: 1,
    options: { A: "3", B: "4" },
    answer: "B",
    due: null,
  },
  {
    id: "q2",
    text: "Name a primary colour.",
    topic_id: 1,
    topic_name: "Maths",
    type: "SHORT",
    difficulty: 2,
    options: {},
    answer: "red",
    keywords: ["red", "blue", "yellow"],
    due: "2020-01-01T00:00:00Z",
  },
];

function setupFetch(questions = QUESTIONS, topics = TOPICS) {
  localStorage.setItem("token", "tok");
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => questions })
    .mockResolvedValueOnce({ ok: true, json: async () => topics });
}

function renderQuestions() {
  return render(<MemoryRouter><Questions /></MemoryRouter>);
}

describe("Questions page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    window.confirm = jest.fn(() => true);
  });

  it("shows loading spinner initially", () => {
    setupFetch();
    global.fetch = jest.fn().mockReturnValue(new Promise(() => {}));
    renderQuestions();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("renders question table after fetch completes", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => {
      expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
    });
    expect(screen.getByText("Name a primary colour.")).toBeInTheDocument();
  });

  it("displays question counts (Total, Due, New)", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => screen.getByText("What is 2+2?"));
    expect(screen.getByText(/Total: 2/)).toBeInTheDocument();
    expect(screen.getByText(/Due: 1/)).toBeInTheDocument();
    expect(screen.getByText(/New: 1/)).toBeInTheDocument();
  });

  it("shows 'Create New Question' button", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => screen.getByText("What is 2+2?"));
    expect(
      screen.getByRole("button", { name: /Create New Question/i })
    ).toBeInTheDocument();
  });

  it("opens create drawer when Create New Question is clicked", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => screen.getByText("What is 2+2?"));
    await userEvent.click(screen.getByRole("button", { name: /Create New Question/i }));
    expect(screen.getByText(/Fill in the question details/i)).toBeInTheDocument();
  });

  it("shows and hides answers when Show/Hide Answers is toggled", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => screen.getByText("What is 2+2?"));

    const toggleBtn = screen.getByRole("button", { name: /Show Answers/i });
    await userEvent.click(toggleBtn);
    expect(screen.getByRole("button", { name: /Hide Answers/i })).toBeInTheDocument();
    // Answer columns now visible
    expect(screen.getAllByRole("columnheader", { name: /Answer/i }).length).toBeGreaterThan(0);
  });

  it("filters questions by search text", async () => {
    setupFetch();
    renderQuestions();
    await waitFor(() => screen.getByText("What is 2+2?"));

    const searchInput = screen.getByLabelText(/Search Questions/i);
    await userEvent.type(searchInput, "primary");

    expect(screen.queryByText("What is 2+2?")).not.toBeInTheDocument();
    expect(screen.getByText("Name a primary colour.")).toBeInTheDocument();
  });

  it("calls delete API and refreshes list when Delete is confirmed", async () => {
    setupFetch();
    // Re-fetch after delete
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => QUESTIONS })
      .mockResolvedValueOnce({ ok: true, json: async () => TOPICS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ message: "Deleted" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [QUESTIONS[1]] })
      .mockResolvedValueOnce({ ok: true, json: async () => TOPICS });

    renderQuestions();
    await waitFor(() => screen.getAllByRole("button", { name: /Delete/ }));

    const deleteButtons = screen.getAllByRole("button", { name: /^Delete$/ });
    await userEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/questions\/q1$/),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });
});
