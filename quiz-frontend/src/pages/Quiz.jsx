import { useState, useEffect, useCallback } from "react";
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
} from "@mui/material";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { useNavigate, useLocation } from "react-router-dom";
import AiChatPanel from "../components/AiChatPanel";

const API_URL = process.env.REACT_APP_API_URL;
const SUPPORTED_TYPES = ["MCQ", "MULTI_MCQ", "NUMERIC", "SHORT", "OPEN"];

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
  const [awaitingOpenRating, setAwaitingOpenRating] = useState(false);
  const [openResponseTimeSeconds, setOpenResponseTimeSeconds] = useState(null);
  const [submittingRating, setSubmittingRating] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationData, setExplanationData] = useState(null);
  const [explanationError, setExplanationError] = useState("");
  const [lastSubmit, setLastSubmit] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  const token = localStorage.getItem("token");
  const topics = location.state?.topics;

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

  useEffect(() => {
    const initializeQuiz = async () => {
      if (!token) {
        navigate("/login");
        return;
      }

      await hasDueQuestionsRemaining();

      const hasQuestion = await fetchNextQuestion();
      if (!hasQuestion) {
        setCurrentQuestion(null);
      }
    };

    initializeQuiz();
  }, [fetchNextQuestion, hasDueQuestionsRemaining, navigate, token]);

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
    return !selectedOption || !String(selectedOption).trim();
  };

  const isInputLocked = !!feedback || awaitingOpenRating;

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
              label={`${key}: ${value}`}
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
              label={`${key}: ${value}`}
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
      try {
        const res = await fetch(`${API_URL}/quiz/submit-answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            question_id: currentQuestion.id,
            selected_option: payloadAnswer,
            response_time: responseTimeSeconds,
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to submit answer");
        }

        if (data.requires_self_rating) {
          setCorrectAnswer(data.correct_answer || "");
          setAwaitingOpenRating(true);
          setOpenResponseTimeSeconds(responseTimeSeconds);
          setLastSubmit({ answer: payloadAnswer, responseTime: responseTimeSeconds });
          return;
        }

        if (data.correct) {
          setScore((prev) => prev + 1);
        }
        setCorrectAnswer(data.correct_answer || "");
        setFeedback(data.correct ? "✅ Correct!" : "❌ Wrong!");
        setLastSubmit({ answer: payloadAnswer, responseTime: responseTimeSeconds });
      } catch (err) {
        console.error(err);
        setFeedback(err instanceof Error ? err.message : "Error submitting answer.");
      }
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
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit answer");
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
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit answer");
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
      navigate("/results", { state: { score, total: answeredCount } });
    }
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
      <Card sx={{ width: 500, p: 2, borderRadius: 3 }}>
        <CardContent>
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

          <Typography variant="h5" gutterBottom>
            Question {questionCount + 1}
          </Typography>
          <Typography variant="subtitle1" sx={{ mb: 2 }}>
            {currentQuestion.text}
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

          {!feedback ? (
            <Button
              variant="contained"
              fullWidth
              sx={{ mt: 2 }}
              onClick={handleSubmit}
              disabled={isSubmitDisabled() || awaitingOpenRating}
            >
              Submit
            </Button>
          ) : (
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
          )}

          {correctAnswer && (
            <Alert severity="info" sx={{ mt: 2 }}>
              Correct answer: {correctAnswer}
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
                <Typography variant="body2" sx={{ color: "inherit" }}>{explanationData.explanation}</Typography>
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
        userAnswer={lastSubmit ? { selected_option: lastSubmit.answer, self_rating: lastSubmit.selfRating ?? null } : {}}
        topicId={currentQuestion?.topic_id}
        initialExplanation={explanationData?.explanation ?? null}
      />
    </Box>
  );
}

export default Quiz;