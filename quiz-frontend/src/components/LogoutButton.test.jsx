import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LogoutButton from "./LogoutButton";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

describe("LogoutButton", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
  });

  it("clears auth storage and navigates to root", async () => {
    localStorage.setItem("token", "token-123");
    localStorage.setItem("user_id", "user-123");

    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: /logout/i }));

    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("user_id")).toBeNull();
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });
});
