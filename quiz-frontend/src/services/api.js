// export const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000";

// export async function getNextQuestion(student_id) {
//   const res = await fetch(`${API_BASE}/next_question?student_id=${student_id}`);
//   if (!res.ok) throw new Error("Failed to fetch question");
//   return res.json();
// }

// export async function submitAnswer(student_id, question_id, selected) {
//   const res = await fetch(`${API_BASE}/submit_answer`, {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ student_id, question_id, selected }),
//   });
//   if (!res.ok) throw new Error("Failed to submit answer");
//   return res.json();
// }

// src/services/api.js
export async function getGreeting() {
  const response = await fetch("http://127.0.0.1:8000/");
  return response.json();
}