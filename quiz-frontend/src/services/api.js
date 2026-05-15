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
const API_URL = process.env.REACT_APP_API_URL;

async function apiGet(path) {
  const token = localStorage.getItem("token");
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function getGreeting() {
  const response = await fetch("http://127.0.0.1:8000/");
  return response.json();
}

export async function getAnalyticsThetaProgression(params = {}) {
  const search = new URLSearchParams();
  if (params.days) search.set("days", String(params.days));
  if (params.topic_id !== undefined && params.topic_id !== null && params.topic_id !== "") {
    search.set("topic_id", String(params.topic_id));
  }
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiGet(`/analytics/theta-progression${suffix}`);
}

export async function getAnalyticsTopicSummary() {
  return apiGet("/analytics/topic-summary");
}

export async function getAnalyticsFsrsRetention(params = {}) {
  const search = new URLSearchParams();
  if (params.days) search.set("days", String(params.days));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiGet(`/analytics/fsrs-retention${suffix}`);
}

export async function getAnalyticsQuestionPerformance(params = {}) {
  const search = new URLSearchParams();
  if (params.days) search.set("days", String(params.days));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiGet(`/analytics/question-performance${suffix}`);
}