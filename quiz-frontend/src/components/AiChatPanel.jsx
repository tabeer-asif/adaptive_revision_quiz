import { useState, useRef, useEffect } from "react";
import {
  Box,
  Typography,
  TextField,
  IconButton,
  Paper,
  Drawer,
  CircularProgress,
  Divider,
  Avatar,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import CloseIcon from "@mui/icons-material/Close";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import PersonIcon from "@mui/icons-material/Person";

const API_URL = process.env.REACT_APP_API_URL;

function AiChatPanel({
  open,
  onClose,
  question,
  userAnswer,
  topicId,
  initialExplanation,
}) {
  const [messages, setMessages] = useState(() =>
    initialExplanation
      ? [{ role: "assistant", content: initialExplanation }]
      : []
  );
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);
  const token = localStorage.getItem("token");

  // Reset messages when the question changes
  useEffect(() => {
    setMessages(
      initialExplanation
        ? [{ role: "assistant", content: initialExplanation }]
        : []
    );
    setInput("");
    setError("");
  }, [question?.id, initialExplanation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setError("");

    // History sent to backend excludes the seeded explanation (that's system context)
    const historyToSend = messages.filter(
      (m) => m.content !== initialExplanation
    );

    try {
      const res = await fetch(`${API_URL}/explanations/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question_id: question.id,
          topic_id: topicId,
          user_answer: userAnswer,
          history: historyToSend,
          message: text,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Chat failed");

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch (err) {
      setError("Something went wrong. Please try again.");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      variant="persistent"
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 400 },
          display: "flex",
          flexDirection: "column",
          height: "100%",
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid",
          borderColor: "divider",
          backgroundColor: "primary.main",
          color: "white",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <SmartToyIcon fontSize="small" />
          <Typography variant="subtitle1" fontWeight={600}>
            AI Tutor
          </Typography>
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: "white" }}>
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Question context */}
      <Box
        sx={{
          px: 2,
          py: 1,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 0.5 }}
        >
          Discussing:
        </Typography>
        <Typography
          variant="body2"
          sx={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {question?.text}
        </Typography>
      </Box>

      {/* Messages */}
      <Box
        sx={{
          flex: 1,
          overflowY: "auto",
          p: 2,
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        {messages.length === 0 && (
          <Box sx={{ textAlign: "center", mt: 4 }}>
            <SmartToyIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
            <Typography variant="body2" color="text.secondary">
              Ask me anything about this question
            </Typography>
          </Box>
        )}

        {messages.map((msg, idx) => (
          <Box
            key={idx}
            sx={{
              display: "flex",
              gap: 1,
              flexDirection: msg.role === "user" ? "row-reverse" : "row",
              alignItems: "flex-start",
            }}
          >
            <Avatar
              sx={{
                width: 28,
                height: 28,
                flexShrink: 0,
                backgroundColor:
                  msg.role === "user" ? "secondary.main" : "primary.main",
              }}
            >
              {msg.role === "user" ? (
                <PersonIcon sx={{ fontSize: 16 }} />
              ) : (
                <SmartToyIcon sx={{ fontSize: 16 }} />
              )}
            </Avatar>

<Paper
              elevation={msg.role === "user" ? 0 : 3}
              sx={{
                p: 1.5,
                maxWidth: "80%",
                ...(msg.role === "user" && {
                  backgroundColor: "primary.main",
                  color: "white",
                }),
                borderRadius:
                  msg.role === "user"
                    ? "12px 12px 2px 12px"
                    : "12px 12px 12px 2px",
              }}
            >
              <Typography
                variant="body2"
                sx={{ whiteSpace: "pre-wrap", color: "inherit" }}
              >
                {msg.content}
              </Typography>
            </Paper>
          </Box>
        ))}

        {loading && (
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Avatar
              sx={{ width: 28, height: 28, backgroundColor: "primary.main" }}
            >
              <SmartToyIcon sx={{ fontSize: 16 }} />
            </Avatar>
            <Paper
              elevation={3}
              sx={{
                p: 1.5,
                borderRadius: "12px 12px 12px 2px",
              }}
            >
              <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
                {[0, 1, 2].map((i) => (
                  <Box
                    key={i}
                    sx={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      backgroundColor: "text.disabled",
                      animation: "pulse 1.2s ease-in-out infinite",
                      animationDelay: `${i * 0.2}s`,
                      "@keyframes pulse": {
                        "0%, 100%": { opacity: 0.3 },
                        "50%": { opacity: 1 },
                      },
                    }}
                  />
                ))}
              </Box>
            </Paper>
          </Box>
        )}

        {error && (
          <Typography
            variant="caption"
            color="error"
            sx={{ textAlign: "center" }}
          >
            {error}
          </Typography>
        )}

        <div ref={bottomRef} />
      </Box>

      {/* Input */}
      <Divider />
      <Box sx={{ p: 2, display: "flex", gap: 1, alignItems: "flex-end" }}>
        <TextField
          fullWidth
          multiline
          maxRows={4}
          size="small"
          placeholder="Ask a follow-up question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <IconButton
          color="primary"
          onClick={sendMessage}
          disabled={!input.trim() || loading}
          sx={{
            backgroundColor: "primary.main",
            color: "white",
            "&:hover": { backgroundColor: "primary.dark" },
            "&:disabled": { backgroundColor: "action.disabledBackground" },
            borderRadius: 2,
            p: 1,
          }}
        >
          {loading ? (
            <CircularProgress size={20} color="inherit" />
          ) : (
            <SendIcon fontSize="small" />
          )}
        </IconButton>
      </Box>
    </Drawer>
  );
}

export default AiChatPanel;
