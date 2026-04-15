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
} from "@mui/material";
import { useNavigate, useLocation } from "react-router-dom";

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
    return data.due_count ?? 0;
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
        throw new Error("Failed to fetch question");
      }

      const data = await res.json();
      // Always clear stale input state when a fresh question arrives.
      setSelectedOption("");
      setSelectedAnswers([]);
      setFeedback("");
      setCurrentQuestion(data);
      setLoading(false);
      setStartTime(Date.now());
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

      const hasDueQuestions = await hasDueQuestionsRemaining();
      if (!hasDueQuestions) {
        setCurrentQuestion(null);
        setLoading(false);
        return;
      }

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
              disabled={!!feedback}
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
                  disabled={!!feedback}
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
          disabled={!!feedback}
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
          disabled={!!feedback}
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
      setFeedback(data.correct ? "✅ Correct!" : "❌ Wrong!");
    } catch (err) {
      console.error(err);
      setFeedback(err instanceof Error ? err.message : "Error submitting answer.");
    }
  };

  const handleNext = async () => {
    setSelectedOption("");
    setSelectedAnswers([]);
    setFeedback("");

    const answeredCount = questionCount + 1;
    setQuestionCount(answeredCount);

    const hasDueQuestions = await hasDueQuestionsRemaining();
    if (!hasDueQuestions) {
      navigate("/results", { state: { score, total: answeredCount } });
      return;
    }

    const hasNextQuestion = await fetchNextQuestion();
    if (!hasNextQuestion) {
      navigate("/results", { state: { score, total: answeredCount } });
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
        <Typography variant="h4">No due questions available</Typography>
      </Box>
    );
  }

  const progress = feedback ? 100 : 0;
  

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
              {` • ${dueQuestionsRemaining} due questions remaining`}
            </Typography>
          </Box>

          <Typography variant="h5" gutterBottom>
            Question {questionCount + 1}
          </Typography>
          <Typography variant="subtitle1" sx={{ mb: 2 }}>
            {currentQuestion.text}
          </Typography>

          {renderAnswerInput()}

          {!feedback ? (
            <Button
              variant="contained"
              fullWidth
              sx={{ mt: 2 }}
              onClick={handleSubmit}
              disabled={isSubmitDisabled()}
            >
              Submit
            </Button>
          ) : (
            <>
              <Alert
                severity={feedback.includes("Correct") ? "success" : "error"}
                sx={{ mt: 2 }}
              >
                {feedback}
              </Alert>
              <Button
                variant="outlined"
                fullWidth
                sx={{ mt: 2 }}
                onClick={handleNext}
              >
                Next
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

export default Quiz;