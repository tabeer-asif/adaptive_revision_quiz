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

export async function getAnalyticsFsrsRatings(params = {}) {
  const search = new URLSearchParams();
  if (params.days) search.set("days", String(params.days));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiGet(`/analytics/fsrs-ratings${suffix}`);
}

export async function getSessionHistory(params = {}) {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiGet(`/sessions/history${suffix}`);
}

export async function getSessionAnswers(sessionId) {
  return apiGet(`/sessions/${sessionId}/answers`);
}