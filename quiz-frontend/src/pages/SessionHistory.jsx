import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  CircularProgress,
  Divider,
  Grid,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { alpha, useTheme } from "@mui/material/styles";
import { getSessionAnswers, getSessionHistory } from "../services/api";

const LIMIT = 20;

function normalizeDateInput(value) {
  if (typeof value !== "string") return value;

  let normalized = value.trim();
  if (!normalized) return normalized;

  if (normalized.includes(" ") && !normalized.includes("T")) {
    normalized = normalized.replace(" ", "T");
  }

  const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized);
  if (!hasTimezone) {
    normalized = `${normalized}Z`;
  }

  return normalized;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(normalizeDateInput(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining.toString().padStart(2, "0")}s`;
}

function getTerminationLabel(value, isActive) {
  if (isActive) return "Active";
  if (value === "max_questions") return "Completed";
  if (value === "se_threshold") return "Confidence stop";
  if (value === "user_quit") return "Ended early";
  return value || "Ended";
}

function formatSelectedOption(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value == null || value === "") return "—";
  return String(value);
}

function SessionHistory() {
  const theme = useTheme();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessions, setSessions] = useState([]);
  const [expandedSessionIds, setExpandedSessionIds] = useState({});
  const [sessionAnswersById, setSessionAnswersById] = useState({});
  const [sessionAnswersLoadingById, setSessionAnswersLoadingById] = useState({});
  const [sessionAnswersErrorById, setSessionAnswersErrorById] = useState({});

  const stats = useMemo(() => {
    const total = sessions.length;
    const completed = sessions.filter((row) => row.termination_reason === "max_questions").length;
    const active = sessions.filter((row) => row.is_active).length;
    const totalQuestions = sessions.reduce((sum, row) => sum + (Number(row.questions_answered) || 0), 0);
    return { total, completed, active, totalQuestions };
  }, [sessions]);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getSessionHistory({ limit: LIMIT });
      setSessions(data.sessions || []);
    } catch (err) {
      setError("Could not load session history. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const toggleSessionExpanded = useCallback(async (sessionId) => {
    const alreadyExpanded = Boolean(expandedSessionIds[sessionId]);
    setExpandedSessionIds((prev) => ({
      ...prev,
      [sessionId]: !alreadyExpanded,
    }));

    if (alreadyExpanded || sessionAnswersById[sessionId] || sessionAnswersLoadingById[sessionId]) {
      return;
    }

    setSessionAnswersLoadingById((prev) => ({ ...prev, [sessionId]: true }));
    setSessionAnswersErrorById((prev) => ({ ...prev, [sessionId]: "" }));

    try {
      const data = await getSessionAnswers(sessionId);
      setSessionAnswersById((prev) => ({
        ...prev,
        [sessionId]: data.answers || [],
      }));
    } catch (err) {
      setSessionAnswersErrorById((prev) => ({
        ...prev,
        [sessionId]: "Could not load question details for this session.",
      }));
    } finally {
      setSessionAnswersLoadingById((prev) => ({ ...prev, [sessionId]: false }));
    }
  }, [expandedSessionIds, sessionAnswersById, sessionAnswersLoadingById]);

  return (
    <Box
      sx={{
        minHeight: "100vh",
        p: { xs: 2, md: 4 },
        background: `linear-gradient(180deg, ${alpha(theme.palette.secondary.main, 0.08)} 0%, ${alpha(
          theme.palette.background.default,
          0.98
        )} 34%, ${theme.palette.background.default} 100%)`,
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
              Past Sessions
            </Typography>
            <Typography color="text.secondary">
              A running history of quiz sessions with duration, question count, and ending reason.
            </Typography>
          </Box>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <Button variant="contained" onClick={loadSessions}>
              Refresh
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
              <Grid item xs={12} sm={3}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Sessions</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {stats.total}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Completed</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {stats.completed}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Active</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {stats.active}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Card sx={{ borderRadius: 3 }}>
                  <CardContent>
                    <Typography color="text.secondary">Questions Answered</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {stats.totalQuestions}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {sessions.length === 0 ? (
              <Card sx={{ borderRadius: 3 }}>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1 }}>
                    No sessions yet
                  </Typography>
                  <Typography color="text.secondary">
                    Start a quiz to begin building your session history.
                  </Typography>
                </CardContent>
              </Card>
            ) : (
              <Stack spacing={2}>
                {sessions.map((session) => (
                  <Card key={session.id} sx={{ borderRadius: 3 }}>
                    <CardContent>
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        alignItems={{ xs: "flex-start", sm: "center" }}
                        justifyContent="space-between"
                        spacing={1.5}
                        sx={{ mb: 2 }}
                      >
                        <Box>
                          <Typography variant="h6" sx={{ fontWeight: 700 }}>
                            {session.topic_summary || session.topic_name || `Session #${session.id}`}
                          </Typography>
                          <Typography color="text.secondary">
                            Started {formatDateTime(session.started_at)}
                          </Typography>
                        </Box>
                        <Chip
                          label={getTerminationLabel(session.termination_reason, session.is_active)}
                          color={session.is_active ? "warning" : "primary"}
                          variant="outlined"
                        />
                      </Stack>

                      <Grid container spacing={2} sx={{ mb: 2 }}>
                        <Grid item xs={12} sm={3}>
                          <Typography variant="caption" color="text.secondary">
                            Questions Answered
                          </Typography>
                          <Typography variant="h6">{session.questions_answered || 0}</Typography>
                        </Grid>
                        <Grid item xs={12} sm={3}>
                          <Typography variant="caption" color="text.secondary">
                            Duration
                          </Typography>
                          <Typography variant="h6">{formatDuration(session.duration_seconds)}</Typography>
                        </Grid>
                        <Grid item xs={12} sm={3}>
                          <Typography variant="caption" color="text.secondary">
                            Estimated Skill Level
                          </Typography>
                          <Typography variant="h6">
                            {typeof session.final_theta === "number"
                              ? session.final_theta.toFixed(2)
                              : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={12} sm={3}>
                          <Typography variant="caption" color="text.secondary">
                            Ended
                          </Typography>
                          <Typography variant="h6">{formatDateTime(session.ended_at)}</Typography>
                        </Grid>
                      </Grid>

                      <Divider sx={{ mb: 1.5 }} />

                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                        {Array.isArray(session.topic_names) && session.topic_names.length > 0
                          ? session.topic_names.map((name) => <Chip key={`${session.id}-${name}`} size="small" label={name} />)
                          : (session.topic_name && <Chip size="small" label={session.topic_name} />)}
                        <IconButton
                          size="small"
                          onClick={() => toggleSessionExpanded(session.id)}
                          aria-label={`Toggle session ${session.id} details`}
                          sx={{ ml: "auto" }}
                        >
                          <ExpandMoreIcon
                            sx={{
                              transform: expandedSessionIds[session.id] ? "rotate(180deg)" : "rotate(0deg)",
                              transition: "transform 0.2s ease",
                            }}
                          />
                        </IconButton>
                      </Stack>

                      <Collapse in={Boolean(expandedSessionIds[session.id])} timeout="auto" unmountOnExit>
                        <Box sx={{ mt: 1.5, pt: 1.5, borderTop: `1px solid ${alpha(theme.palette.divider, 0.7)}` }}>
                          <Typography variant="subtitle2" sx={{ mb: 1 }}>
                            Questions answered in this session
                          </Typography>

                          {sessionAnswersLoadingById[session.id] ? (
                            <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
                              <CircularProgress size={22} />
                            </Box>
                          ) : sessionAnswersErrorById[session.id] ? (
                            <Alert severity="error" sx={{ mt: 1 }}>
                              {sessionAnswersErrorById[session.id]}
                            </Alert>
                          ) : (sessionAnswersById[session.id] || []).length === 0 ? (
                            <Typography variant="body2" color="text.secondary">
                              No answered questions recorded for this session.
                            </Typography>
                          ) : (
                            <Stack spacing={1}>
                              {(sessionAnswersById[session.id] || []).map((answer) => (
                                <Box
                                  key={`${session.id}-${answer.index}-${answer.question_id}`}
                                  sx={{
                                    border: `1px solid ${alpha(theme.palette.divider, 0.8)}`,
                                    borderRadius: 2,
                                    px: 1.5,
                                    py: 1,
                                  }}
                                >
                                  <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                      {answer.index}. {answer.question_text}
                                    </Typography>
                                    <Chip
                                      size="small"
                                      label={answer.correct ? "Correct" : "Wrong"}
                                      color={answer.correct ? "success" : "error"}
                                      variant="outlined"
                                    />
                                  </Stack>
                                  <Typography variant="caption" color="text.secondary">
                                    Your answer: {formatSelectedOption(answer.selected_option)}
                                  </Typography>
                                </Box>
                              ))}
                            </Stack>
                          )}
                        </Box>
                      </Collapse>
                    </CardContent>
                  </Card>
                ))}
              </Stack>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}

export default SessionHistory;