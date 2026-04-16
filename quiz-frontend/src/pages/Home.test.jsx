import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Home from "./Home";

process.env.REACT_APP_API_URL = "http://api.test";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const TOPICS = [
  { id: 1, name: "Maths" },
  { id: 2, name: "Science" },
];

function renderHome() {
  return render(<MemoryRouter><Home /></MemoryRouter>);
}

describe("Home page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
    localStorage.clear();
  });

  it("redirects to /login when no token in storage", async () => {
    renderHome();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/login");
    });
  });

  it("shows loading spinner initially then renders topics", async () => {
    localStorage.setItem("token", "tok");
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => TOPICS,
    });

    renderHome();
    // Loading spinner visible before fetch resolves
    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Welcome 👋")).toBeInTheDocument();
    });

    // Topics dropdown loaded
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/topics$/),
      expect.any(Object)
    );
  });

  it("Start Quiz button is disabled when no topic selected", async () => {
    localStorage.setItem("token", "tok");
    global.fetch.mockResolvedValue({ ok: true, json: async () => TOPICS });

    renderHome();
    await screen.findByLabelText(/Topics/i);

    expect(screen.getByRole("button", { name: /Start Quiz/i })).toBeDisabled();
  });

  it("navigates to /questions when View Question Database is clicked", async () => {
    localStorage.setItem("token", "tok");
    global.fetch.mockResolvedValue({ ok: true, json: async () => TOPICS });

    renderHome();
    await screen.findByRole("button", { name: /View Question Database/i });

    await userEvent.click(screen.getByRole("button", { name: /View Question Database/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/questions");
  });

  it("clears storage and navigates to / on logout", async () => {
    localStorage.setItem("token", "tok");
    localStorage.setItem("user_id", "u1");
    global.fetch.mockResolvedValue({ ok: true, json: async () => TOPICS });

    renderHome();
    await screen.findByRole("button", { name: /Logout/i });

    await userEvent.click(screen.getByRole("button", { name: /Logout/i }));

    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("user_id")).toBeNull();
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("handles fetch error gracefully and hides spinner", async () => {
    localStorage.setItem("token", "tok");
    global.fetch.mockRejectedValue(new Error("Network error"));

    renderHome();
    await waitFor(() => {
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });
  });
});
