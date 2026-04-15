process.env.REACT_APP_API_URL = "http://api.test";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

describe("Login page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
    localStorage.clear();
  });

  it("shows validation error when fields are empty", async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    expect(screen.getByText("Please fill in all fields.")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("shows validation error for invalid email", async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/email/i), "invalid-email");
    await userEvent.type(screen.getByLabelText(/password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    expect(screen.getByText("Please enter a valid email address.")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("stores token and navigates to home on successful login", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ access_token: "test-token", user_id: "user-1" }),
    });

    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/auth\/login$/),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "user@example.com", password: "password123" }),
        }
      );
    });

    expect(localStorage.getItem("token")).toBe("test-token");
    expect(localStorage.getItem("user_id")).toBe("user-1");
    expect(mockNavigate).toHaveBeenCalledWith("/home");
  });

  it("shows error when API returns non-JSON content type", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      headers: { get: () => "text/html" },
      json: async () => ({})
    });

    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "password123");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => {
      expect(
        screen.getByText("API URL is incorrect or frontend env is stale. Railway returned HTML instead of JSON.")
      ).toBeInTheDocument();
    });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("shows error when API returns non-ok status", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      headers: { get: () => "application/json" },
      json: async () => ({ detail: "Invalid credentials" }),
    });

    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpassword");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });

    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
