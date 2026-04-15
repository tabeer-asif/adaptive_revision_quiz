import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Box
} from "@mui/material";

const API_URL = process.env.REACT_APP_API_URL;

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  const isValidEmail = (email) => {
    return /\S+@\S+\.\S+/.test(email);
  };

  const handleLogin = async () => {
    setError("");

    // ✅ Frontend validation
    if (!email || !password) {
      setError("Please fill in all fields.");
      return;
    }

    if (!isValidEmail(email)) {
      setError("Please enter a valid email address.");
      return;
    }

    try {
      setLoading(true);

      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email, password })
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Invalid email or password");
      }

      // ✅ Store token
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user_id", data.user_id);

      // ✅ Redirect to home
      navigate("/home");

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
    return (
    <Box
        sx={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        }}
    >
        <Card sx={{ width: 400, p: 2, borderRadius: 3 }}>
        <CardContent>
            <Typography variant="h4" gutterBottom align="center">
            Login
            </Typography>

            <TextField
            label="Email"
            type="email"
            fullWidth
            margin="normal"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            />

            <TextField
            label="Password"
            type="password"
            fullWidth
            margin="normal"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            />

            <Button
            variant="contained"
            fullWidth
            sx={{ mt: 2, height: 45 }}
            onClick={handleLogin}
            disabled={loading}
            >
            {loading ? <CircularProgress size={24} /> : "Login"}
            </Button>

            {/* ✅ Error message */}
            {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
                {error}
            </Alert>
            )}

            <Typography variant="body2" sx={{ mt: 2 }} align="center">
            Don't have an account?{" "}
            <Link to="/register">Register here</Link>
            </Typography>
        </CardContent>
        </Card>
    </Box>
    );
}

export default Login;