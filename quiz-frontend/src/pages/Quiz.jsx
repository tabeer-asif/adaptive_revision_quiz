import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  RadioGroup,
  FormControlLabel,
  Radio,
  Checkbox,
  TextField,
  Button,
  CircularProgress,
  Alert,
  LinearProgress,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Chip,
} from "@mui/material";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { useNavigate, useLocation } from "react-router-dom";
import AiChatPanel from "../components/AiChatPanel";
import MathText from "../components/MathText";

const API_URL = process.env.REACT_APP_API_URL;
const SUPPORTED_TYPES = ["MCQ", "MULTI_MCQ", "NUMERIC", "SHORT", "OPEN"];
const OPEN_MIN_ANSWER_LENGTH = 20;
function formatDifficultyChipLabel(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `Difficulty: ${Math.min(5, Math.max(1, Math.round(value)))}`;
  }
  if (typeof value === "string" && value.trim()) {
    return `Difficulty: ${value.trim()}`;
  }
  return "Difficulty: Unspecified";
}

function Quiz() {
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [selectedOption, setSelectedOption] = useState("");
  const [selectedAnswers, setSelectedAnswers] = useState([]);
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);
  const [score, setScore] = useState(0);
  const [questionCount, setQuestionCount] = useState(0);
  const [startTime, setStartTime] = useState(null);
  const [dueQuestionsRemaining, setDueQuestionsRemaining] = useState(0);
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [openFeedbackData, setOpenFeedbackData] = useState(null);
  const [openFeedbackLoading, setOpenFeedbackLoading] = useState(false);
  const [openSelfMarkLoading, setOpenSelfMarkLoading] = useState(false);
  const [openFeedbackError, setOpenFeedbackError] = useState("");
  const [awaitingOpenRating, setAwaitingOpenRating] = useState(false);
  const [openResponseTimeSeconds, setOpenResponseTimeSeconds] = useState(null);
  const [submittingRating, setSubmittingRating] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationData, setExplanationData] = useState(null);
  const [explanationError, setExplanationError] = useState("");
  const [lastSubmit, setLastSubmit] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [exitDialogOpen, setExitDialogOpen] = useState(false);

  const sessionIdRef = useRef(null);
  const sessionStartPromiseRef = useRef(null);
  const lastThetaRef = useRef(null);
  const sessionEndedRef = useRef(false);
  const sessionCloseRequestedRef = useRef(false);
  const sessionCloseReasonRef = useRef("user_quit");
  const sessionLifecycleBoundRef = useRef(false);

  const navigate = useNavigate();
  const location = useLocation();

  const token = localStorage.getItem("token");
  const topics = location.state?.topics;
  const sessionTopicId = Array.isArray(topics) && topics.length === 1 ? topics[0] : null;
  const sessionTopicIds = useMemo(
    () => (Array.isArray(topics)
      ? topics
          .map((id) => Number(id))
          .filter((id) => Number.isInteger(id) && id > 0)
      : []),
    [topics]
  );

  const endSession = useCallback(async (terminationReason) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId || sessionEndedRef.current) return null;

    sessionEndedRef.current = true;
    try {
      const payload = {
        termination_reason: terminationReason,
      };

      if (typeof lastThetaRef.current === "number") {
        payload.final_theta = lastThetaRef.current;
      }

      const res = await fetch(`${API_URL}/sessions/${activeSessionId}/end`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to end session");
      }

      const data = await res.json();
      return data;
    } catch (err) {
      console.error(err);
      return null;
    }
  }, [token]);

  const startSession = useCallback(async () => {
    if (sessionIdRef.current) return sessionIdRef.current;
    if (sessionStartPromiseRef.current) return sessionStartPromiseRef.current;

    const startPromise = (async () => {
      try {
        const res = await fetch(`${API_URL}/sessions/start`, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            topic_id: sessionTopicId,
            topic_ids: sessionTopicIds.length > 0 ? sessionTopicIds : undefined,
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to start session");
        }

        sessionIdRef.current = data.id;
        sessionEndedRef.current = false;

        if (sessionCloseRequestedRef.current) {
          void endSession(sessionCloseReasonRef.current);
        }

        return data.id;
      } catch (err) {
        console.error(err);
        return null;
      } finally {
        sessionStartPromiseRef.current = null;
      }
    })();

    sessionStartPromiseRef.current = startPromise;
    return startPromise;
  }, [endSession, sessionTopicId, sessionTopicIds, token]);

  const requestSessionClose = useCallback((reason) => {
    sessionCloseRequestedRef.current = true;
    sessionCloseReasonRef.current = reason;

    if (sessionIdRef.current) {
      void endSession(reason);
    }
  }, [endSession]);

  const getDueCount = useCallback(async () => {
    const res = await fetch(`${API_URL}/questions/due/count`, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });

    if (!res.ok) {
      throw new Error("Failed to fetch due count");
    }

    const data = await res.json();
    return data.total_available ?? 0;
  }, [token]);

  const fetchNextQuestion = useCallback(async () => {
    const headers = {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    };

    let fetchUrl = `${API_URL}/questions/irt`;
    let fetchOptions = { headers };

    if (topics && topics.length > 0) {
      fetchUrl = `${API_URL}/questions/irt/by-topics`;
      fetchOptions = {
        method: "POST",
        headers,
        body: JSON.stringify({ topics }),
      };
    }

    try {
      const res = await fetch(fetchUrl, fetchOptions);

      if (!res.ok) {
        if (res.status === 404) {
          setCurrentQuestion(null);
          setLoading(false);
          return false;
        }
        throw new Error("Failed to fetch question");
      }

      const data = await res.json();
      // Always clear stale input state when a fresh question arrives.
      setSelectedOption("");
      setSelectedAnswers([]);
      setFeedback("");
      setCorrectAnswer("");
      setOpenFeedbackData(null);
      setOpenFeedbackLoading(false);
      setOpenFeedbackError("");
      setAwaitingOpenRating(false);
      setOpenResponseTimeSeconds(null);
      setSubmittingRating(false);
      setCurrentQuestion(data);
      setLoading(false);
      setStartTime(Date.now());
      setLastSubmit(null);
      setExplanationData(null);
      setExplanationLoading(false);
      setExplanationError("");
      setChatOpen(false);
      return true;
    } catch (err) {
      console.error(err);
      setLoading(false);
      setFeedback("Error fetching next question.");
      return false;
    }
  }, [token, topics]);

  const hasDueQuestionsRemaining = useCallback(async () => {
    try {
      const dueCount = await getDueCount();
      setDueQuestionsRemaining(dueCount);
      return dueCount > 0;
    } catch (err) {
      console.error(err);
      setFeedback("Error checking due questions.");
      return false;
    }
  }, [getDueCount]);

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    if (sessionLifecycleBoundRef.current) return undefined;
    sessionLifecycleBoundRef.current = true;

    const initializeQuiz = async () => {
      if (!token) {
        navigate("/login");
        return;
      }

      await startSession();
      await hasDueQuestionsRemaining();

      const hasQuestion = await fetchNextQuestion();
      if (!hasQuestion) {
        setCurrentQuestion(null);
      }
    };

    initializeQuiz();
    return () => {
      requestSessionClose("user_quit");
    };
    // The session lifecycle should be bound once per page mount.
    // Re-running this effect can trigger premature cleanup/end calls.
  }, []);
  /* eslint-enable react-hooks/exhaustive-deps */

  const buildAnswer = () => {
    const type = currentQuestion?.type;
    if (type === "MULTI_MCQ") return selectedAnswers;
    if (type === "NUMERIC") {
      const parsed = Number(selectedOption);
      return Number.isFinite(parsed) ? parsed : null;
    }
    if (!["MCQ", "SHORT", "OPEN"].includes(type)) return null;
    return selectedOption;
  };

  const isSubmitDisabled = () => {
    const type = currentQuestion?.type;
    if (!SUPPORTED_TYPES.includes(type)) return true;
    if (type === "MULTI_MCQ") return selectedAnswers.length === 0;
    if (type === "NUMERIC") {
      if (!String(selectedOption).trim()) return true;
      return !Number.isFinite(Number(selectedOption));
    }
    if (type === "OPEN") {
      return String(selectedOption || "").trim().length < OPEN_MIN_ANSWER_LENGTH;
    }
    return !selectedOption || !String(selectedOption).trim();
  };

  const isInputLocked = !!feedback || awaitingOpenRating || openFeedbackLoading || openSelfMarkLoading;
  const openAnswerLoading = openFeedbackLoading || openSelfMarkLoading;

  const renderAnswerInput = () => {
    const type = currentQuestion.type;

    if (type === "MCQ") {
      return (
        <RadioGroup
          value={selectedOption}
          onChange={(e) => setSelectedOption(e.target.value)}
        >
          {Object.entries(currentQuestion.options || {}).map(([key, value]) => (
            <FormControlLabel
              key={key}
              value={key}
              control={<Radio />}
              label={<><strong>{key}:</strong> <MathText text={value} /></>}
              disabled={isInputLocked}
            />
          ))}
        </RadioGroup>
      );
    }

    if (type === "MULTI_MCQ") {
      return (
        <Box>
          {Object.entries(currentQuestion.options || {}).map(([key, value]) => (
            <FormControlLabel
              key={key}
              control={
                <Checkbox
                  checked={selectedAnswers.includes(key)}
                  onChange={() =>
                    setSelectedAnswers((prev) =>
                      prev.includes(key)
                        ? prev.filter((k) => k !== key)
                        : [...prev, key]
                    )
                  }
                  disabled={isInputLocked}
                />
              }
              label={<><strong>{key}:</strong> <MathText text={value} /></>}
            />
          ))}
        </Box>
      );
    }

    if (type === "NUMERIC") {
      return (
        <TextField
          label="Your answer"
          type="number"
          fullWidth
          value={selectedOption}
          onChange={(e) => setSelectedOption(e.target.value)}
          disabled={isInputLocked}
          sx={{ mt: 1 }}
        />
      );
    }

    if (type === "SHORT" || type === "OPEN") {
      return (
        <TextField
          label="Your answer"
          fullWidth
          multiline
          minRows={type === "OPEN" ? 4 : 2}
          value={selectedOption}
          onChange={(e) => setSelectedOption(e.target.value)}
          disabled={isInputLocked}
          sx={{ mt: 1 }}
        />
      );
    }

    return (
      <Alert severity="warning" sx={{ mt: 1 }}>
        Unsupported question type: {String(type || "Unknown")}
      </Alert>
    );
  };

  const handleSubmit = async () => {
    if (isSubmitDisabled()) return;

    const payloadAnswer = buildAnswer();
    if (payloadAnswer == null) {
      setFeedback("Unsupported or invalid answer format.");
      return;
    }

    const endTime = Date.now();
    const responseTime = endTime - startTime;
    const responseTimeSeconds = responseTime / 1000;

    if (currentQuestion?.type === "OPEN") {
      await handlePersonalisedFeedback(payloadAnswer, responseTimeSeconds);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/quiz/submit-answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json",  Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          selected_option: payloadAnswer,
          response_time: responseTimeSeconds,
          session_id: sessionIdRef.current,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit answer");
      }

      if (typeof data.theta_after === "number") {
        lastThetaRef.current = data.theta_after;
      }

      if (data.correct) {
        setScore(prev => prev + 1);
      }
      setCorrectAnswer(data.correct_answer || "");
      setFeedback(data.correct ? "✅ Correct!" : "❌ Wrong!");
      setLastSubmit({ answer: payloadAnswer, responseTime: responseTimeSeconds });
    } catch (err) {
      console.error(err);
      setFeedback(err instanceof Error ? err.message : "Error submitting answer.");
    }
  };

  const handlePersonalisedFeedback = async (payloadAnswerArg = null, responseTimeSecondsArg = null) => {
    if (!currentQuestion || currentQuestion.type !== "OPEN") return;

    const payloadAnswer = payloadAnswerArg ?? buildAnswer();
    const responseTimeSeconds = responseTimeSecondsArg ?? ((Date.now() - startTime) / 1000);

    if (payloadAnswer == null) {
      setFeedback("Unsupported or invalid answer format.");
      return;
    }

    setOpenFeedbackLoading(true);
    setOpenFeedbackError("");
    try {
      const res = await fetch(`${API_URL}/feedback/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          student_answer: String(payloadAnswer),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Could not generate feedback. Please try again.");
      }

      setOpenFeedbackData({
        strengths: data.strengths,
        gaps: data.gaps,
        hint: data.hint,
        encouragement: data.encouragement,
      });
      setCorrectAnswer(data.model_answer || "");
      setFeedback("");
      setAwaitingOpenRating(true);
      setOpenResponseTimeSeconds(responseTimeSeconds);
      setLastSubmit({ answer: payloadAnswer, responseTime: responseTimeSeconds });
    } catch (err) {
      console.error(err);
      setOpenFeedbackError(err instanceof Error ? err.message : "Could not generate feedback. Please try again.");
    } finally {
      setOpenFeedbackLoading(false);
    }
  };

  const handleSelfMark = async () => {
    if (!currentQuestion || currentQuestion.type !== "OPEN") return;

    const payloadAnswer = buildAnswer();
    if (payloadAnswer == null) {
      setFeedback("Unsupported or invalid answer format.");
      return;
    }

    const responseTimeSeconds = (Date.now() - startTime) / 1000;

    setOpenSelfMarkLoading(true);
    setOpenFeedbackError("");
    setOpenFeedbackData(null);
    try {
      const res = await fetch(`${API_URL}/quiz/submit-answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          selected_option: String(payloadAnswer),
          response_time: responseTimeSeconds,
          session_id: sessionIdRef.current,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit answer");
      }

      if (typeof data.theta_after === "number") {
        lastThetaRef.current = data.theta_after;
      }

      setCorrectAnswer(data.correct_answer || "");
      setFeedback("");
      setAwaitingOpenRating(true);
      setOpenResponseTimeSeconds(responseTimeSeconds);
      setLastSubmit({ answer: payloadAnswer, responseTime: responseTimeSeconds });
    } catch (err) {
      console.error(err);
      setFeedback(err instanceof Error ? err.message : "Error submitting answer.");
    } finally {
      setOpenSelfMarkLoading(false);
    }
  };

  const handleOpenRating = async (rating) => {
    if (!currentQuestion || !awaitingOpenRating || submittingRating) return;

    const payloadAnswer = buildAnswer();
    if (payloadAnswer == null || openResponseTimeSeconds == null) {
      setFeedback("Unsupported or invalid answer format.");
      return;
    }

    setSubmittingRating(true);
    try {
      const res = await fetch(`${API_URL}/quiz/submit-answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          selected_option: payloadAnswer,
          response_time: openResponseTimeSeconds,
          self_rating: rating,
          session_id: sessionIdRef.current,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit answer");
      }

      if (typeof data.theta_after === "number") {
        lastThetaRef.current = data.theta_after;
      }

      if (data.correct) {
        setScore((prev) => prev + 1);
      }

      setCorrectAnswer(data.correct_answer || correctAnswer);
      setAwaitingOpenRating(false);
      setOpenResponseTimeSeconds(null);
      setFeedback("Response saved.");
      setLastSubmit((prev) => prev ? { ...prev, selfRating: rating } : null);
    } catch (err) {
      console.error(err);
      setFeedback(err instanceof Error ? err.message : "Error submitting answer.");
    } finally {
      setSubmittingRating(false);
    }
  };

  const handleNext = async () => {
    setSelectedOption("");
    setSelectedAnswers([]);
    setFeedback("");
    setCorrectAnswer("");
    setOpenFeedbackData(null);
    setOpenFeedbackLoading(false);
    setOpenSelfMarkLoading(false);
    setOpenFeedbackError("");
    setAwaitingOpenRating(false);
    setOpenResponseTimeSeconds(null);
    setSubmittingRating(false);
    setExplanationData(null);
    setExplanationLoading(false);
    setExplanationError("");
    setLastSubmit(null);
    setChatOpen(false);

    const answeredCount = questionCount + 1;
    setQuestionCount(answeredCount);

    await hasDueQuestionsRemaining();

    const hasNextQuestion = await fetchNextQuestion();
    if (!hasNextQuestion) {
      const endedSession = await endSession("max_questions");
      const backendAnswered = Number(endedSession?.questions_answered);
      const total = Number.isFinite(backendAnswered) ? backendAnswered : answeredCount;
      navigate("/results", {
        state: {
          score,
          total,
          feedback: endedSession?.feedback ?? null,
        },
      });
    }
  };

  const handleExitQuiz = () => {
    setExitDialogOpen(true);
  };

  const confirmExitQuiz = async () => {
    requestSessionClose("user_quit");
    const endedSession = await endSession("user_quit");
    const backendAnswered = Number(endedSession?.questions_answered);
    const total = Number.isFinite(backendAnswered) ? backendAnswered : questionCount;
    setExitDialogOpen(false);
    navigate("/results", {
      state: {
        score,
        total,
        exitedEarly: true,
        feedback: endedSession?.feedback ?? null,
      },
    });
  };

  const cancelExitQuiz = () => {
    setExitDialogOpen(false);
  };

  const handleExplain = async () => {
    if (!currentQuestion || !lastSubmit) return;
    setExplanationLoading(true);
    setExplanationData(null);
    setExplanationError("");
    try {
      const res = await fetch(`${API_URL}/explanations/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          topic_id: currentQuestion.topic_id,
          selected_option: lastSubmit.answer,
          self_rating: lastSubmit.selfRating ?? null,
          response_time: lastSubmit.responseTime,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to fetch explanation");
      setExplanationData(data);
    } catch (err) {
      setExplanationError(err instanceof Error ? err.message : "Error fetching explanation.");
    } finally {
      setExplanationLoading(false);
    }
  };

  if (loading)
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
        }}
      >
        <CircularProgress />
      </Box>
    );

  if (!currentQuestion) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
        }}
      >
        <Typography variant="h4">No questions available</Typography>
      </Box>
    );
  }

  const progress = (feedback || awaitingOpenRating) ? 100 : 0;
    const openAnswerLength = String(selectedOption || "").trim().length;
    const openRemainingChars = Math.max(0, OPEN_MIN_ANSWER_LENGTH - openAnswerLength);

  const feedbackSeverity = feedback.includes("Correct")
    ? "success"
    : feedback.includes("Wrong") || feedback.toLowerCase().includes("error") || feedback.toLowerCase().includes("failed")
      ? "error"
      : "info";
  

  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        p: 2,
      }}
    >
      <Card
        sx={{
          width: "100%",
          maxWidth: { xs: 560, md: 760 },
          p: 2,
          borderRadius: 3,
        }}
      >
        <CardContent>
          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, mb: 1 }}>
            <Button variant="outlined" color="warning" size="small" onClick={handleExitQuiz}>
              Exit Quiz
            </Button>
          </Box>

          {/* Progress Bar */}
          <Box sx={{ width: "100%", mb: 2 }}>
            <LinearProgress
              variant="determinate"
              value={progress}
              sx={{ height: 10, borderRadius: 5 }}
            />
            <Typography variant="caption" sx={{ mt: 0.5, display: "block", textAlign: "center" }}>
              {questionCount} completed so far
              {` • ${dueQuestionsRemaining} questions remaining`}
            </Typography>
          </Box>

          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 1, mb: 1.25 }}>
            <Typography variant="h5" sx={{ mb: 0 }}>
              Question {questionCount + 1}
            </Typography>
            <Chip
              label={formatDifficultyChipLabel(currentQuestion.difficulty)}
              size="small"
              variant="outlined"
            />
          </Box>
          <Typography variant="subtitle1" component="div" sx={{ mb: 2 }}>
            <MathText text={currentQuestion.text} />
          </Typography>

          {currentQuestion.image_url && (
            <Box sx={{ mb: 2, textAlign: "center" }}>
              <img
                src={currentQuestion.image_url}
                alt="Question illustration"
                style={{ maxWidth: "100%", maxHeight: 260, borderRadius: 6 }}
              />
            </Box>
          )}

          {renderAnswerInput()}

          {currentQuestion.type === "OPEN" && !openFeedbackData && !feedback && !awaitingOpenRating && (
            <Typography variant="caption" sx={{ mt: 1, display: "block", color: openRemainingChars > 0 ? "text.secondary" : "success.main" }}>
              {openRemainingChars > 0
                ? `Minimum ${openRemainingChars} more characters`
                : "Ready to submit for feedback"}
            </Typography>
          )}

          {currentQuestion.type === "OPEN" && !feedback && !openFeedbackData && !awaitingOpenRating ? (
            <Box sx={{ display: "flex", gap: 1, mt: 2, flexDirection: { xs: "column", sm: "row" } }}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleSelfMark}
                disabled={isSubmitDisabled() || openAnswerLoading}
              >
                {openSelfMarkLoading ? "Saving..." : "Self Mark"}
              </Button>
              <Button
                variant="contained"
                fullWidth
                onClick={handlePersonalisedFeedback}
                disabled={isSubmitDisabled() || openAnswerLoading}
              >
                {openFeedbackLoading ? "Getting feedback..." : "Want personalised feedback"}
              </Button>
            </Box>
          ) : !feedback && !openFeedbackData && !awaitingOpenRating ? (
            <Button
              variant="contained"
              fullWidth
              sx={{ mt: 2 }}
              onClick={handleSubmit}
              disabled={isSubmitDisabled() || awaitingOpenRating || openAnswerLoading}
            >
              {openFeedbackLoading ? "Getting feedback..." : "Submit"}
            </Button>
          ) : (
            feedback && (
              <>
              <Alert
                severity={feedbackSeverity}
                sx={{ mt: 2 }}
              >
                {feedback}
              </Alert>
              <Box sx={{ display: "flex", gap: 1, mt: 2 }}>
                <Button
                  variant="outlined"
                  fullWidth
                  onClick={handleNext}
                >
                  Next
                </Button>
                <Button
                  variant="outlined"
                  color="secondary"
                  fullWidth
                  onClick={handleExplain}
                  disabled={explanationLoading}
                  startIcon={explanationLoading ? <CircularProgress size={16} /> : null}
                >
                  {explanationLoading ? "Loading…" : "Explain this"}
                </Button>
              </Box>
              </>
            )
          )}

          {openFeedbackError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {openFeedbackError}
            </Alert>
          )}

          {openFeedbackData && (
            <Paper elevation={2} sx={{ mt: 2, p: 2, borderRadius: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                AI feedback
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>What you did well:</strong> {openFeedbackData.strengths}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>What to improve:</strong> {openFeedbackData.gaps}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>Hint:</strong> {openFeedbackData.hint}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {openFeedbackData.encouragement}
              </Typography>
            </Paper>
          )}

          {correctAnswer && (
            <Alert severity="info" sx={{ mt: 2 }} component="div">
              Correct answer: <MathText text={correctAnswer} />
            </Alert>
          )}

          {explanationError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {explanationError}
            </Alert>
          )}

          {explanationData && (
            <Box sx={{ mt: 2 }}>
              <Paper elevation={3} sx={{ p: 2, borderRadius: 2, borderLeft: "3px solid", borderLeftColor: "primary.main" }}>
                <Typography variant="body2" component="div" sx={{ color: "inherit", whiteSpace: "pre-line" }}>
                  <MathText text={explanationData.explanation} />
                </Typography>
              </Paper>
              <Button
                variant="outlined"
                color="secondary"
                size="small"
                startIcon={<SmartToyIcon />}
                sx={{ mt: 1 }}
                onClick={() => setChatOpen(true)}
              >
                Still confused? Ask a question
              </Button>
            </Box>
          )}

          {awaitingOpenRating && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                How did this feel?
              </Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1 }}>
                <Button
                  variant="outlined"
                  onClick={() => handleOpenRating(4)}
                  disabled={submittingRating}
                  sx={{ color: "success.main", borderColor: "success.main", bgcolor: "success.50", "&:hover": { bgcolor: "success.100", borderColor: "success.dark" } }}
                >
                  Easy
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => handleOpenRating(3)}
                  disabled={submittingRating}
                  sx={{ color: "info.main", borderColor: "info.main", bgcolor: "info.50", "&:hover": { bgcolor: "info.100", borderColor: "info.dark" } }}
                >
                  Good
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => handleOpenRating(2)}
                  disabled={submittingRating}
                  sx={{ color: "warning.main", borderColor: "warning.main", bgcolor: "warning.50", "&:hover": { bgcolor: "warning.100", borderColor: "warning.dark" } }}
                >
                  Hard
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => handleOpenRating(1)}
                  disabled={submittingRating}
                  sx={{ color: "error.main", borderColor: "error.main", bgcolor: "error.50", "&:hover": { bgcolor: "error.100", borderColor: "error.dark" } }}
                >
                  Again
                </Button>
              </Box>
            </Box>
          )}
        </CardContent>
      </Card>

      <AiChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        question={currentQuestion}
        userAnswer={lastSubmit ? {
          selected_option: lastSubmit.answer,
          self_rating: lastSubmit.selfRating ?? null,
          open_feedback: currentQuestion?.type === "OPEN" && openFeedbackData
            ? {
                strengths: openFeedbackData.strengths,
                gaps: openFeedbackData.gaps,
                hint: openFeedbackData.hint,
                encouragement: openFeedbackData.encouragement,
              }
            : null,
        } : {}}
        topicId={currentQuestion?.topic_id}
        initialExplanation={explanationData?.explanation ?? null}
      />

      <Dialog open={exitDialogOpen} onClose={cancelExitQuiz}>
        <DialogTitle>Exit quiz early?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            You can leave now and keep the progress from the questions you have already completed.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelExitQuiz}>Cancel</Button>
          <Button color="warning" variant="contained" onClick={confirmExitQuiz}>
            Exit Quiz
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Quiz;