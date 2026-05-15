import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  BarChart,
  Bar,
} from "recharts";
import {
  getAnalyticsFsrsRetention,
  getAnalyticsQuestionPerformance,
  getAnalyticsThetaProgression,
  getAnalyticsTopicSummary,
} from "../services/api";

const WINDOW_OPTIONS = [30, 90, 180, 365];

function EmptyCard({ title, description }) {
  return (
    <Card sx={{ borderRadius: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {title}
        </Typography>
        <Typography color="text.secondary">{description}</Typography>
      </CardContent>
    </Card>
  );
}

function Analytics() {
  const navigate = useNavigate();
  const [windowDays, setWindowDays] = useState(90);
  const [thetaTopicFilter, setThetaTopicFilter] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [topicSummary, setTopicSummary] = useState([]);
  const [thetaSeries, setThetaSeries] = useState([]);
  const [fsrsSummary, setFsrsSummary] = useState({ overdue: 0, due_today: 0, due_in_window: 0 });
  const [dueTrend, setDueTrend] = useState([]);
  const [stabilityTrend, setStabilityTrend] = useState([]);
  const [questionRows, setQuestionRows] = useState([]);

  const topicOptions = useMemo(() => {
    return topicSummary.map((row) => ({
      id: row.topic_id,
      name: row.topic_name || `Topic ${row.topic_id}`,
    }));
  }, [topicSummary]);

  // Auto-select first topic once series data arrives
  useEffect(() => {
    if (thetaSeries.length > 0 && thetaTopicFilter === null) {
      setThetaTopicFilter(String(thetaSeries[0].topic_id));
    }
  }, [thetaSeries]);

  const activeThetaSeries = useMemo(() => {
    return thetaSeries.find((s) => String(s.topic_id) === String(thetaTopicFilter)) || null;
  }, [thetaSeries, thetaTopicFilter]);

  const loadAnalytics = async () => {
    setLoading(true);
    setError("");
    try {
      const [summaryRes, thetaRes, fsrsRes, performanceRes] = await Promise.all([
        getAnalyticsTopicSummary(),
        getAnalyticsThetaProgression({ days: windowDays }),
        getAnalyticsFsrsRetention({ days: windowDays }),
        getAnalyticsQuestionPerformance({ days: windowDays }),
      ]);

      setTopicSummary(summaryRes.topics || []);
      setThetaSeries(thetaRes.series || []);
      setFsrsSummary(fsrsRes.summary || { overdue: 0, due_today: 0, due_in_window: 0 });
      setDueTrend(fsrsRes.due_counts_over_time || []);
      setStabilityTrend(fsrsRes.stability_trend || []);
      setQuestionRows((performanceRes.questions || []).slice(0, 12));
    } catch (err) {
      setError("Could not load analytics data. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, [windowDays]);

  return (
    <Box
      sx={{
        minHeight: "100vh",
        p: { xs: 2, md: 4 },
        background: "linear-gradient(180deg, #f4f8fb 0%, #edf2f7 100%)",
      }}
    >
      <Box sx={{ maxWidth: 1200, mx: "auto" }}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          alignItems={{ xs: "flex-start", md: "center" }}
          justifyContent="space-between"
          spacing={2}
          sx={{ mb: 3 }}
        >
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700 }}>
              Learning Analytics
            </Typography>
            <Typography color="text.secondary">
              Evidence dashboard for adaptive theta progression, FSRS retention, and IRT performance.
            </Typography>
          </Box>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="window-label">Window</InputLabel>
              <Select
                labelId="window-label"
                label="Window"
                value={windowDays}
                onChange={(e) => setWindowDays(e.target.value)}
              >
                {WINDOW_OPTIONS.map((days) => (
                  <MenuItem key={days} value={days}>
                    Last {days} days
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Button variant="contained" onClick={loadAnalytics}>
              Retry
            </Button>
            <Button variant="outlined" onClick={() => navigate("/home")}>Back to Home</Button>
          </Stack>
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 12 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={4}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Overdue Cards</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>{fsrsSummary.overdue || 0}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Due Today</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>{fsrsSummary.due_today || 0}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Due In Window</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>{fsrsSummary.due_in_window || 0}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Card sx={{ borderRadius: 3, mb: 1 }}>
                  <CardContent sx={{ display: "flex", alignItems: "center", gap: 2, py: "12px !important" }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600, mr: 1 }}>
                      Theta Progression — Topic Filter
                    </Typography>
                    <FormControl size="small" sx={{ minWidth: 200 }}>
                      <InputLabel id="theta-topic-filter-label">Topic</InputLabel>
                      <Select
                        labelId="theta-topic-filter-label"
                        label="Topic"
                        value={thetaTopicFilter || ""}
                        onChange={(e) => setThetaTopicFilter(e.target.value)}
                      >
                        {topicOptions.map((topic) => (
                          <MenuItem key={topic.id} value={String(topic.id)}>
                            {topic.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </CardContent>
                </Card>

                {!activeThetaSeries ? (
                  <EmptyCard
                    title="Theta Progression"
                    description="No theta progression data yet for the selected topic."
                  />
                ) : (
                  <Card sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Typography color="text.secondary" sx={{ mb: 2 }}>
                        Theta Before / After Over Time
                      </Typography>
                      <Box sx={{ width: "100%", height: 300 }}>
                        <ResponsiveContainer>
                          <LineChart
                            data={activeThetaSeries.points || []}
                            margin={{ top: 8, right: 20, bottom: 16, left: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="created_at" hide />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="theta_before" stroke="#64748b" dot={false} name="Theta Before" />
                            <Line type="monotone" dataKey="theta_after" stroke="#0f766e" dot={false} name="Theta After" />
                          </LineChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>
                )}
              </Grid>

              <Grid item xs={12} md={6}>
                {dueTrend.length === 0 ? (
                  <EmptyCard
                    title="FSRS Due Count Trend"
                    description="No upcoming due-card trend available in this time window."
                  />
                ) : (
                  <Card sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2 }}>FSRS Due Counts Over Time</Typography>
                      <Box sx={{ width: "100%", height: 280 }}>
                        <ResponsiveContainer>
                          <BarChart data={dueTrend}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="date" hide />
                            <YAxis />
                            <Tooltip />
                            <Bar dataKey="due_count" fill="#0ea5e9" />
                          </BarChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>
                )}
              </Grid>

              <Grid item xs={12} md={6}>
                {stabilityTrend.length === 0 ? (
                  <EmptyCard
                    title="FSRS Stability Trend"
                    description="No stability history is available yet for this window."
                  />
                ) : (
                  <Card sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2 }}>Average Stability Trend</Typography>
                      <Box sx={{ width: "100%", height: 280 }}>
                        <ResponsiveContainer>
                          <LineChart data={stabilityTrend}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="date" hide />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="avg_stability" stroke="#0f766e" dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>
                )}
              </Grid>

              <Grid item xs={12}>
                {topicSummary.length === 0 ? (
                  <EmptyCard
                    title="Topic Theta Summary"
                    description="No topic-level theta values have been calibrated yet."
                  />
                ) : (
                  <Card sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2 }}>Current Theta By Topic</Typography>
                      <Box sx={{ width: "100%", height: 300 }}>
                        <ResponsiveContainer>
                          <BarChart data={topicSummary}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="topic_name" />
                            <YAxis />
                            <Tooltip />
                            <Bar dataKey="theta" fill="#0f766e" name="Theta" />
                          </BarChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>
                )}
              </Grid>

              <Grid item xs={12}>
                {questionRows.length === 0 ? (
                  <EmptyCard
                    title="Question Performance"
                    description="No question attempts found for this time window."
                  />
                ) : (
                  <Card sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2 }}>Question Pass Rate vs IRT b Drift</Typography>
                      <Box sx={{ width: "100%", height: 320 }}>
                        <ResponsiveContainer>
                          <LineChart data={questionRows}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="question_id" />
                            <YAxis yAxisId="left" domain={[0, 1]} />
                            <YAxis yAxisId="right" orientation="right" />
                            <Tooltip />
                            <Legend />
                            <Line yAxisId="left" type="monotone" dataKey="pass_rate" stroke="#0ea5e9" name="Pass Rate" />
                            <Line yAxisId="right" type="monotone" dataKey="irt_b_drift" stroke="#f97316" name="IRT b Drift" />
                          </LineChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>
                )}
              </Grid>
            </Grid>
          </>
        )}
      </Box>
    </Box>
  );
}

export default Analytics;
