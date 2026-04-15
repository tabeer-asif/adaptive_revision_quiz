process.env.REACT_APP_API_URL = "http://api.test";

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PrivateRoute from "./PrivateRoute";

describe("PrivateRoute", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
    localStorage.clear();
  });

  function renderRoute() {
    return render(
      <MemoryRouter initialEntries={["/protected"]}>
        <Routes>
          <Route
            path="/protected"
            element={
              <PrivateRoute>
                <div>Protected Content</div>
              </PrivateRoute>
            }
          />
          <Route path="/" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("shows loading while verifying token", () => {
    localStorage.setItem("token", "any-token");
    // never resolves – keeps loading state visible
    global.fetch.mockReturnValue(new Promise(() => {}));
    renderRoute();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("redirects to login when no token is present", async () => {
    renderRoute();
    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("renders children when token verification succeeds", async () => {
    localStorage.setItem("token", "valid-token");
    global.fetch.mockResolvedValue({ ok: true });
    renderRoute();
    await waitFor(() => {
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/auth\/verify-token$/),
      { headers: { Authorization: "Bearer valid-token" } }
    );
  });

  it("redirects to login when token verification fails", async () => {
    localStorage.setItem("token", "invalid-token");
    global.fetch.mockResolvedValue({ ok: false });
    renderRoute();
    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });
  });
});
