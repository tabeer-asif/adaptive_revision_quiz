import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Register from "./Register";

process.env.REACT_APP_API_URL = "http://api.test";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderRegister() {
  return render(<MemoryRouter><Register /></MemoryRouter>);
}

describe("Register page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("renders all form fields and register button", () => {
    renderRegister();
    expect(screen.getByLabelText(/First Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Surname/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Register/i })).toBeInTheDocument();
  });

  it("shows error when fields are empty", async () => {
    renderRegister();
    await userEvent.click(screen.getByRole("button", { name: /Register/i }));
    expect(screen.getByText("All fields are required.")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("shows error for invalid email", async () => {
    renderRegister();
    await userEvent.type(screen.getByLabelText(/First Name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/Surname/i), "Doe");
    await userEvent.type(screen.getByLabelText(/Email/i), "notanemail");
    await userEvent.type(screen.getByLabelText(/Password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /Register/i }));
    expect(screen.getByText("Please enter a valid email address.")).toBeInTheDocument();
  });

  it("shows error for short password", async () => {
    renderRegister();
    await userEvent.type(screen.getByLabelText(/First Name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/Surname/i), "Doe");
    await userEvent.type(screen.getByLabelText(/Email/i), "jane@example.com");
    await userEvent.type(screen.getByLabelText(/Password/i), "abc");
    await userEvent.click(screen.getByRole("button", { name: /Register/i }));
    expect(screen.getByText("Password must be at least 6 characters.")).toBeInTheDocument();
  });

  it("shows success message and redirects on successful registration", async () => {
    jest.useFakeTimers();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ message: "ok" }),
    });

    renderRegister();
    await userEvent.type(screen.getByLabelText(/First Name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/Surname/i), "Doe");
    await userEvent.type(screen.getByLabelText(/Email/i), "jane@example.com");
    await userEvent.type(screen.getByLabelText(/Password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /Register/i }));

    await waitFor(() => {
      expect(screen.getByText(/Registration successful/i)).toBeInTheDocument();
    });

    jest.runAllTimers();
    expect(mockNavigate).toHaveBeenCalledWith("/");
    jest.useRealTimers();
  });

  it("shows error when registration API call fails", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Email already in use" }),
    });

    renderRegister();
    await userEvent.type(screen.getByLabelText(/First Name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/Surname/i), "Doe");
    await userEvent.type(screen.getByLabelText(/Email/i), "jane@example.com");
    await userEvent.type(screen.getByLabelText(/Password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /Register/i }));

    await waitFor(() => {
      expect(screen.getByText("Email already in use")).toBeInTheDocument();
    });
  });
});
