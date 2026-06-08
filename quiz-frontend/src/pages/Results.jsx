// src/pages/Results.jsx
import { useLocation, useNavigate } from "react-router-dom";
import { Box, Card, CardContent, Typography, Button, LinearProgress, Stack, Divider } from "@mui/material";

function Results() {
  const location = useLocation();
  const navigate = useNavigate();

  const score = location.state?.score || 0;
  const total = Math.max(0, Number(location.state?.total ?? 0));
  const exitedEarly = Boolean(location.state?.exitedEarly);
  const feedback = location.state?.feedback || null;

  const percentage = total > 0 ? Math.round((score / total) * 100) : 0;

  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
      }}
    >
      <Card sx={{ width: 450, p: 3, borderRadius: 3 }}>
        <CardContent>
          <Typography variant="h4" align="center" gutterBottom>
            🎉 Results
          </Typography>

          <Typography variant="h6" align="center" sx={{ mb: 2 }}>
            You scored {score} out of {total}
          </Typography>

          {exitedEarly && (
            <Typography align="center" color="text.secondary" sx={{ mb: 2 }}>
              Quiz ended early. Your progress so far is saved in this summary.
            </Typography>
          )}

          {/* Progress bar */}
          <LinearProgress
            variant="determinate"
            value={percentage}
            sx={{ height: 10, borderRadius: 5, mb: 2 }}
          />

          <Typography align="center" sx={{ mb: 3 }}>
            {percentage}% Accuracy
          </Typography>

          {feedback && (
            <Card variant="outlined" sx={{ mb: 3, borderRadius: 2, backgroundColor: "rgba(25, 118, 210, 0.04)" }}>
              <CardContent>
                <Stack spacing={1.25}>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    Session feedback
                  </Typography>
                  {feedback.headline && (
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      {feedback.headline}
                    </Typography>
                  )}
                  {feedback.strengths && (
                    <Typography variant="body2">
                      <strong>Strengths:</strong> {feedback.strengths}
                    </Typography>
                  )}
                  {feedback.weaknesses && (
                    <Typography variant="body2">
                      <strong>Needs work:</strong> {feedback.weaknesses}
                    </Typography>
                  )}
                  {feedback.trend && (
                    <Typography variant="body2">
                      <strong>Trend:</strong> {feedback.trend}
                    </Typography>
                  )}
                  {feedback.action && (
                    <>
                      <Divider />
                      <Typography variant="body2">
                        <strong>Next step:</strong> {feedback.action}
                      </Typography>
                    </>
                  )}
                </Stack>
              </CardContent>
            </Card>
          )}

          {/* ✅ General Feedback message */}
          <Typography align="center" sx={{ mt: 2, mb: 3 }}>
            {total === 0
              ? "Start another quiz whenever you're ready."
              : percentage >= 80
              ? "🔥 Great job! You're mastering this topic."
              : percentage >= 50
              ? "📘 Keep practicing — you're getting there!"
              : "⚠️ You need more review. Don't worry, repetition helps!"}
          </Typography>

          {/* Buttons */}
          <Button
            variant="contained"
            fullWidth
            sx={{ mb: 2 }}
            onClick={() => navigate("/quiz")}
          >
            Try Again
          </Button>

          <Button
            variant="outlined"
            fullWidth
            onClick={() => navigate("/home")}
          >
            Back to Home
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}

export default Results;