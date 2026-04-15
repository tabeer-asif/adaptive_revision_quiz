// src/pages/Results.jsx
import { useLocation, useNavigate } from "react-router-dom";
import { Box, Card, CardContent, Typography, Button, LinearProgress } from "@mui/material";

function Results() {
  const location = useLocation();
  const navigate = useNavigate();

  const score = location.state?.score || 0;
  const total = location.state?.total || 1;

  const percentage = Math.round((score / total) * 100);

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

          {/* Progress bar */}
          <LinearProgress
            variant="determinate"
            value={percentage}
            sx={{ height: 10, borderRadius: 5, mb: 2 }}
          />

          <Typography align="center" sx={{ mb: 3 }}>
            {percentage}% Accuracy
          </Typography>

          {/* ✅ General Feedback message */}
          <Typography align="center" sx={{ mt: 2, mb: 3 }}>
            {percentage >= 80
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