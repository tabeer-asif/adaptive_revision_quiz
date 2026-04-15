
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  OutlinedInput,
  CircularProgress
} from "@mui/material";

const API_URL = process.env.REACT_APP_API_URL;

function Home() {
  const navigate = useNavigate();
  const [topicsList, setTopicsList] = useState([]);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      navigate("/login"); // Redirect if no token
      return;
    }

    // Fetch topics from backend
    fetch(`${API_URL}/topics`, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch topics");
        return res.json();
      })
      .then((data) => {
        setTopicsList(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch topics:", err);
        setLoading(false);
      });
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_id");
    navigate("/");
  };

  const handleStartQuiz = () => {
    navigate("/quiz", { state: { topics: selectedTopics } });
  };

  if (loading) {
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
  }

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
      <Card sx={{ width: 400, p: 3, borderRadius: 3 }}>
        <CardContent>
          <Typography variant="h4" align="center" gutterBottom>
            Welcome 👋
          </Typography>

          <Typography variant="body1" align="center" sx={{ mb: 3 }}>
            Ready to test your knowledge? Select your topics below:
          </Typography>

          {/* Topic Selector */}
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel id="topic-select-label">Topics</InputLabel>
            <Select
              labelId="topic-select-label"
              multiple
              value={selectedTopics}
              onChange={(e) => setSelectedTopics(e.target.value)}
              input={<OutlinedInput label="Topics" />}
              renderValue={(selected) => (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {selected.map((id) => {
                    const topic = topicsList.find((t) => t.id === id);
                    return <Chip key={id} label={topic?.name || id} />;
                  })}
                </Box>
              )}
            >
              {topicsList.map((topic) => (
                <MenuItem key={topic.id} value={topic.id}>
                  {topic.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Button
            variant="contained"
            fullWidth
            sx={{ mb: 2, height: 45 }}
            onClick={handleStartQuiz}
            disabled={selectedTopics.length === 0} // Require at least 1 topic
          >
            Start Quiz
          </Button>
          <Button
            variant="outlined"
            fullWidth
            sx={{ mb: 2, height: 45 }}
            onClick={() => navigate("/questions")}
          >
            View Question Database
          </Button>

          <Button
            variant="outlined"
            color="error"
            fullWidth
            sx={{ height: 45 }}
            onClick={handleLogout}
          >
            Logout
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}

export default Home;
