// src/components/LogoutButton.jsx
import { useNavigate } from "react-router-dom";
import { Button } from "@mui/material";

export default function LogoutButton() {
  const navigate = useNavigate();

  const handleLogout = () => {
    // Clear local storage
    localStorage.removeItem("token");
    localStorage.removeItem("user_id");

    // Redirect to login
    navigate("/");
  };

  return (
    <Button
      variant="outlined"
      color="secondary"
      onClick={handleLogout}
    >
      Logout
    </Button>
  );
}