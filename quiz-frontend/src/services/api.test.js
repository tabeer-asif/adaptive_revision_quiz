import { getGreeting } from "./api";

describe("api.js – getGreeting", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("fetches the greeting endpoint and returns JSON", async () => {
    global.fetch.mockResolvedValue({
      json: async () => ({ message: "Hello" }),
    });

    const result = await getGreeting();

    expect(global.fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/");
    expect(result).toEqual({ message: "Hello" });
  });
});
