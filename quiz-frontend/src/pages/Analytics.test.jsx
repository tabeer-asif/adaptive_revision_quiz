import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Analytics from "./Analytics";

jest.mock("recharts", () => {
  const Mock = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Mock,
    LineChart: Mock,
    BarChart: Mock,
    CartesianGrid: Mock,
    Legend: Mock,
    Line: Mock,
    ReferenceLine: Mock,
    XAxis: Mock,
    YAxis: Mock,
    Tooltip: Mock,
    Bar: Mock,
  };
});

jest.mock("../services/api", () => ({
  getAnalyticsTopicSummary: jest.fn(),
  getAnalyticsThetaProgression: jest.fn(),
  getAnalyticsFsrsRetention: jest.fn(),
  getAnalyticsQuestionPerformance: jest.fn(),
}));

const {
  getAnalyticsTopicSummary,
  getAnalyticsThetaProgression,
  getAnalyticsFsrsRetention,
  getAnalyticsQuestionPerformance,
} = require("../services/api");

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderAnalytics() {
  return render(
    <MemoryRouter>
      <Analytics />
    </MemoryRouter>
  );
}

describe("Analytics page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getAnalyticsTopicSummary.mockResolvedValue({
      topics: [{ topic_id: 1, topic_name: "Biology", theta: 0.5, n_responses: 12 }],
    });
    getAnalyticsThetaProgression.mockResolvedValue({
      series: [
        {
          topic_id: 1,
          topic_name: "Biology",
          points: [{ created_at: "2026-05-01", theta_before: 0.1, theta_after: 0.2, posterior_sd: 0.9 }],
        },
      ],
    });
    getAnalyticsFsrsRetention.mockResolvedValue({
      summary: { overdue: 1, due_today: 2, due_in_window: 8 },
      due_counts_over_time: [{ date: "2026-05-07", due_count: 2 }],
      stability_trend: [{ date: "2026-05-07", avg_stability: 2.5 }],
    });
    getAnalyticsQuestionPerformance.mockResolvedValue({
      questions: [{ question_id: 11, pass_rate: 0.7, irt_b_drift: 0.1 }],
    });
  });

  it("loads and renders headline analytics cards", async () => {
    renderAnalytics();

    await waitFor(() => {
      expect(screen.getByText(/Learning Analytics/i)).toBeInTheDocument();
      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("8")).toBeInTheDocument();
    });
  });

  it("shows error alert and allows retry", async () => {
    getAnalyticsTopicSummary.mockRejectedValueOnce(new Error("boom"));

    renderAnalytics();

    await waitFor(() => {
      expect(screen.getByText(/Could not load analytics data/i)).toBeInTheDocument();
    });

    getAnalyticsTopicSummary.mockResolvedValueOnce({ topics: [] });
    getAnalyticsThetaProgression.mockResolvedValueOnce({ series: [] });
    getAnalyticsFsrsRetention.mockResolvedValueOnce({
      summary: { overdue: 0, due_today: 0, due_in_window: 0 },
      due_counts_over_time: [],
      stability_trend: [],
    });
    getAnalyticsQuestionPerformance.mockResolvedValueOnce({ questions: [] });

    await userEvent.click(screen.getByRole("button", { name: /Retry/i }));

    await waitFor(() => {
      expect(getAnalyticsTopicSummary).toHaveBeenCalledTimes(2);
    });
  });

  it("navigates back to home", async () => {
    renderAnalytics();
    await waitFor(() => expect(getAnalyticsTopicSummary).toHaveBeenCalled());

    await userEvent.click(screen.getByRole("button", { name: /Back to Home/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/home");
  });
});
