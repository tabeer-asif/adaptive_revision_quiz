process.env.REACT_APP_API_URL = "http://api.test";

import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";

describe("App routing", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    localStorage.clear();
  });

  it("renders the Login page on the root path", async () => {
    // jsdom starts at about:blank; App wraps with BrowserRouter
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Login/i })).toBeInTheDocument();
    });
  });
});
