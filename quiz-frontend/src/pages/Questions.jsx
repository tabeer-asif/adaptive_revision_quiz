import { useCallback, useEffect, useMemo, useState } from "react";
import MathText from "../components/MathText";
import {
  Box,
  Typography,
  CircularProgress,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Pagination,
  Button,
  Drawer,
  Alert,
  Divider,
  Checkbox,
  FormControlLabel,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  LinearProgress,
  IconButton,
  Tooltip,
} from "@mui/material";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { useNavigate } from "react-router-dom";

// ─── Constants ───────────────────────────────────────────────────────────────
const API_URL = process.env.REACT_APP_API_URL;
const QUESTION_TYPES = ["MCQ", "MULTI_MCQ", "NUMERIC", "SHORT", "OPEN"];
// Bloom-aligned weights per difficulty level. 0.0 = incompatible at that level.
const TYPE_DIFFICULTY_WEIGHTS = {
  MCQ:       [1.8, 1.6, 1.2, 0.0, 0.0],
  SHORT:     [1.6, 1.4, 1.2, 0.4, 0.0],
  NUMERIC:   [0.8, 1.2, 1.4, 1.2, 1.0],
  MULTI_MCQ: [0.0, 0.4, 1.2, 1.4, 1.6],
  OPEN:      [0.0, 0.0, 0.8, 1.6, 1.8],
};
const TYPE_BLOOM_MAP = {
  MCQ: "Remember/Understand - recognition and basic interpretation",
  MULTI_MCQ: "Understand/Analyse - evaluate each option",
  NUMERIC: "Apply - execute method or formula",
  SHORT: "Remember/Understand - recall without options",
  OPEN: "Evaluate/Create - justify, critique, synthesise",
};
const TYPE_INFO_MAP = {
  MCQ: "Single correct option from multiple choices.",
  MULTI_MCQ: "Multiple correct options can be selected.",
  NUMERIC: "Answer is a number, checked within a tolerance range.",
  SHORT: "Brief free text response, requiring a short phrase at most.",
  OPEN: "Long form response requiring explanation or reasoning.",
};
const FILTER_CONTROL_HEIGHT = 56; // px — keeps all filter-row controls the same height

const findLatexDelimiterIssues = (value) => {
  if (typeof value !== "string" || !value.trim()) return [];

  const issues = [];
  const tokenRegex = /\\\(|\\\)|\\\[|\\\]/g;
  let inlineDepth = 0;
  let blockDepth = 0;

  for (const token of value.match(tokenRegex) || []) {
    if (token === "\\(") {
      inlineDepth += 1;
      continue;
    }
    if (token === "\\)") {
      if (inlineDepth === 0) {
        issues.push("Found \\) without matching \\(.");
      } else {
        inlineDepth -= 1;
      }
      continue;
    }
    if (token === "\\[") {
      blockDepth += 1;
      continue;
    }
    if (token === "\\]") {
      if (blockDepth === 0) {
        issues.push("Found \\] without matching \\[.");
      } else {
        blockDepth -= 1;
      }
    }
  }

  if (inlineDepth > 0) issues.push("Unclosed inline math delimiter: \\( ... \\)");
  if (blockDepth > 0) issues.push("Unclosed block math delimiter: \\[ ... \\]");

  if (value.includes("$")) {
    issues.push("Dollar delimiters are legacy. Use \\( ... \\) or \\[ ... \\].");
  }

  return [...new Set(issues)];
};

const allocateTypeCounts = (selectedTypes, count, difficulty) => {
  const ordered = QUESTION_TYPES.filter((t) => selectedTypes.includes(t));
  if (!ordered.length || count <= 0) return {};

  const diffIdx = Math.max(0, Math.min(4, Number(difficulty) - 1));
  const weights = Object.fromEntries(
    ordered.map((t) => [t, TYPE_DIFFICULTY_WEIGHTS[t][diffIdx]])
  );
  const eligible = ordered.filter((t) => weights[t] > 0);

  const counts = Object.fromEntries(ordered.map((t) => [t, 0]));
  if (!eligible.length) return counts;

  const guaranteed = count >= eligible.length ? eligible.length : 0;
  if (guaranteed > 0) {
    eligible.forEach((t) => { counts[t] = 1; });
  }

  const remaining = count - guaranteed;
  if (remaining <= 0) return counts;

  const weightSum = eligible.reduce((a, t) => a + weights[t], 0) || eligible.length;
  const rawAlloc = Object.fromEntries(
    eligible.map((t) => [t, remaining * (weights[t] / weightSum)])
  );
  const floored = Object.fromEntries(
    eligible.map((t) => [t, Math.floor(rawAlloc[t])])
  );

  eligible.forEach((t) => { counts[t] += floored[t]; });

  const used = eligible.reduce((sum, t) => sum + floored[t], 0);
  const leftovers = remaining - used;
  if (leftovers > 0) {
    const ranked = [...eligible].sort((a, b) => {
      const fracDiff = (rawAlloc[b] - floored[b]) - (rawAlloc[a] - floored[a]);
      if (fracDiff !== 0) return fracDiff;
      return QUESTION_TYPES.indexOf(a) - QUESTION_TYPES.indexOf(b);
    });
    for (let i = 0; i < leftovers; i += 1) {
      counts[ranked[i]] += 1;
    }
  }

  return counts;
};

// ─── Initial form state factory ──────────────────────────────────────────────
// Called both on mount and after a successful create/edit to reset the drawer.
const createInitialFormState = () => ({
  topic_id: "",
  text: "",
  type: "",
  options: [
    { key: "A", value: "" },
    { key: "B", value: "" },
  ],
  answer: "",
  answers: [],
  difficulty: "1",
  tolerance: "",
  keywords: [""],
  image_url: "",
  imageUploading: false,
});

// ─── Date helpers ────────────────────────────────────────────────────────────

const parseDueDate = (due) => {
  if (!due) return null;

  const dueStr = String(due).trim();
  if (!dueStr) return null;

  // Treat timezone-naive values as UTC to avoid local-time shifts.
  const normalized = /([zZ]|[+-]\d{2}:\d{2})$/.test(dueStr)
    ? dueStr
    : `${dueStr}Z`;

  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

// Returns true if a question's due date has passed (i.e. ready for review).
const isDueNow = (due) => {
  const parsed = parseDueDate(due);
  return parsed ? parsed.getTime() <= Date.now() : false;
};

// Uploads a file to Supabase Storage and calls back with the resulting URL.
const uploadQuestionImage = async (file, token, { onStart, onUrl, onError, onFinally } = {}) => {
  onStart?.();
  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/uploads/question-image`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    onUrl?.(data.image_url);
  } catch (err) {
    onError?.(err.message || "Image upload failed");
  } finally {
    onFinally?.();
  }
};

function Questions() {
  const navigate = useNavigate();
  // ── Data ──────────────────────────────────────────────────────────────────
  const [questions, setQuestions] = useState([]);     // full list from API
  const [topics, setTopics] = useState([]);           // all available topics
  const [loading, setLoading] = useState(true);

  // ── Table filter / sort / pagination ──────────────────────────────────────
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("");           // "" | "difficulty" | "due"
  const [topicFilter, setTopicFilter] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [sortOrder, setSortOrder] = useState("asc");  // "asc" | "desc"
  const [showAnswers, setShowAnswers] = useState(false);

  // ── Row selection (for bulk delete) ───────────────────────────────────────
  const [selectedQuestionIds, setSelectedQuestionIds] = useState([]);

  // ── Create / Edit drawer ──────────────────────────────────────────────────
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingQuestionId, setEditingQuestionId] = useState(null); // null = creating new
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [questionForm, setQuestionForm] = useState(createInitialFormState);

  // ── Inline topic creation (inside drawer) ─────────────────────────────────
  const [newTopicName, setNewTopicName] = useState("");
  const [newTopicError, setNewTopicError] = useState("");
  const [creatingTopic, setCreatingTopic] = useState(false);

  // ── AI generation dialog ───────────────────────────────────────────────────
  const [aiDialogOpen, setAiDialogOpen] = useState(false);
  const [aiStep, setAiStep] = useState(1);             // 1 = upload form, 2 = review
  const [aiFile, setAiFile] = useState(null);
  const [aiTopicId, setAiTopicId] = useState("");
  const [aiDefaultTopicId, setAiDefaultTopicId] = useState("");
  const [aiSuggestedTopics, setAiSuggestedTopics] = useState([]);
  const [aiSuggestedNewTopicNames, setAiSuggestedNewTopicNames] = useState([]);
  const [aiReviewTopicName, setAiReviewTopicName] = useState("");
  const [aiReviewTopicError, setAiReviewTopicError] = useState("");
  const [aiCreatingReviewTopic, setAiCreatingReviewTopic] = useState(false);
  const [aiSelectedTypes, setAiSelectedTypes] = useState(new Set());
  const [aiDifficultyDistribution, setAiDifficultyDistribution] = useState({ 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 });
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiGeneratedQuestions, setAiGeneratedQuestions] = useState([]);
  const [aiWarnings, setAiWarnings] = useState([]);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiSaveError, setAiSaveError] = useState("");
  const [aiFileFeasibility, setAiFileFeasibility] = useState(null); // null | { scores: {MCQ,NUMERIC,...} }
  const [aiFeasibilityLoading, setAiFeasibilityLoading] = useState(false);
  const [aiEditingKey, setAiEditingKey] = useState(null); // _key of question being edited inline
  const [aiProgress, setAiProgress] = useState({ stage: "", percent: 0 });

  const latexIssues = useMemo(() => {
    const optionIssues = questionForm.options.map((option) =>
      findLatexDelimiterIssues(option?.value || "")
    );
    const textIssues = findLatexDelimiterIssues(questionForm.text);
    const answerIssues = ["SHORT", "OPEN"].includes(questionForm.type)
      ? findLatexDelimiterIssues(questionForm.answer)
      : [];

    const hasAnyIssues =
      textIssues.length > 0 ||
      answerIssues.length > 0 ||
      optionIssues.some((arr) => arr.length > 0);

    return {
      textIssues,
      optionIssues,
      answerIssues,
      hasAnyIssues,
    };
  }, [questionForm]);

  const orderedSelectedTypes = QUESTION_TYPES.filter((type) => aiSelectedTypes.has(type));
  const plannedTypeSplitByDifficulty = [1, 2, 3, 4, 5]
    .map((level) => {
      const requested = aiDifficultyDistribution[level] || 0;
      return {
        level,
        requested,
        split: allocateTypeCounts(orderedSelectedTypes, requested, level),
      };
    })
    .filter((entry) => entry.requested > 0);
  const hasCompatibleGenerationPlan = plannedTypeSplitByDifficulty.some(({ split }) =>
    Object.values(split).some((allocatedCount) => allocatedCount > 0)
  );

  const token = localStorage.getItem("token");

  // Fetches the full question list with FSRS card data merged in (due date, last review, etc.).
  const fetchQuestions = useCallback(async () => {
    const res = await fetch(`${API_URL}/questions/overview`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error("Failed to fetch questions");
    }

    return res.json();
  }, [token]);

  // Fetches all topics for the topic filter dropdown and the drawer topic selector.
  const fetchTopics = useCallback(async () => {
    const res = await fetch(`${API_URL}/topics`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error("Failed to fetch topics");
    }

    return res.json();
  }, [token]);

  // Re-fetches questions and clears the selection (called after create/edit/delete).
  const refreshQuestions = useCallback(async () => {
    const refreshedQuestions = await fetchQuestions();
    setQuestions(refreshedQuestions);
    setSelectedQuestionIds([]);
  }, [fetchQuestions]);



  // Uploads a file and stores the returned URL in the drawer form state.
  const handleImageUpload = (file) =>
    uploadQuestionImage(file, token, {
      onStart:   () => { updateQuestionForm("imageUploading", true); setFormError(""); },
      onUrl:     (url) => updateQuestionForm("image_url", url),
      onError:   (msg) => setFormError(msg),
      onFinally: () => updateQuestionForm("imageUploading", false),
    });

  // Uploads a file for a specific AI-review question, storing uploading state by _key.
  const [aiQuestionUploading, setAiQuestionUploading] = useState({});
  const handleAiQuestionImageUpload = (key, file) =>
    uploadQuestionImage(file, token, {
      onStart:   () => setAiQuestionUploading((prev) => ({ ...prev, [key]: true })),
      onUrl:     (url) => updateAiQuestion(key, { image_url: url }),
      onError:   (msg) => setAiSaveError(msg),
      onFinally: () => setAiQuestionUploading((prev) => ({ ...prev, [key]: false })),
    });

  // ─── Topic creation ───────────────────────────────────────────────────────

  // POSTs a new topic, refreshes the topic list, and auto-selects the new topic in the form.
  const handleCreateTopic = async () => {
    const name = newTopicName.trim();
    if (!name) {
      setNewTopicError("Topic name cannot be empty");
      return;
    }
    setCreatingTopic(true);
    setNewTopicError("");
    try {
      const res = await fetch(`${API_URL}/topics`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create topic");
      }
      const topicData = await fetchTopics();
      setTopics(topicData);
      updateQuestionForm("topic_id", String(data.id));
      setNewTopicName("");
    } catch (err) {
      setNewTopicError(err.message || "Failed to create topic");
    } finally {
      setCreatingTopic(false);
    }
  };

  // ─── Initial data load ───────────────────────────────────────────────────

  // Loads questions and topics in parallel on mount.
  useEffect(() => {
    const loadData = async () => {
      try {
        const [questionData, topicData] = await Promise.all([
          fetchQuestions(),
          fetchTopics(),
        ]);

        setQuestions(questionData);
        setTopics(topicData);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [fetchQuestions, fetchTopics]);

  // ─── Form field handlers ─────────────────────────────────────────────────

  // Generic single-field updater for the question form.
  const updateQuestionForm = (field, value) => {
    setQuestionForm((prev) => ({ ...prev, [field]: value }));
  };

  // Difficulty input: only allows whole-number characters.
  const handleDifficultyChange = (value) => {
    if (/^\d*$/.test(value)) {
      updateQuestionForm("difficulty", value);
    }
  };

  // Changing question type resets type-specific fields but preserves topic/text/difficulty.
  const handleTypeChange = (type) => {
    setFormError("");
    setQuestionForm((prev) => ({
      ...createInitialFormState(),
      topic_id: prev.topic_id,
      text: prev.text,
      difficulty: prev.difficulty,
      type,
    }));
  };

  // ─── MCQ / MULTI_MCQ option management ──────────────────────────────────

  // Updates a single option's key or value, keeping selected answers in sync.
  const handleOptionChange = (index, field, value) => {
    setQuestionForm((prev) => {
      const nextOptions = [...prev.options];
      nextOptions[index] = { ...nextOptions[index], [field]: value };

      const nextAnswers = prev.answers.filter((answerKey) =>
        nextOptions.some((option) => option.key === answerKey)
      );
      const nextAnswer = nextOptions.some((option) => option.key === prev.answer)
        ? prev.answer
        : "";

      return {
        ...prev,
        options: nextOptions,
        answers: nextAnswers,
        answer: nextAnswer,
      };
    });
  };

  // Appends a new option with the next letter key (C, D, E…).
  const addOption = () => {
    setQuestionForm((prev) => ({
      ...prev,
      options: [
        ...prev.options,
        { key: String.fromCharCode(65 + prev.options.length), value: "" },
      ],
    }));
  };

  // Removes an option and clears it from the selected answer(s) if it was chosen.
  // Minimum of 2 options is enforced.
  const removeOption = (index) => {
    setQuestionForm((prev) => {
      if (prev.options.length <= 2) {
        return prev;
      }

      const removedOption = prev.options[index];
      const nextOptions = prev.options.filter((_, optionIndex) => optionIndex !== index);

      return {
        ...prev,
        options: nextOptions,
        answer: prev.answer === removedOption.key ? "" : prev.answer,
        answers: prev.answers.filter((key) => key !== removedOption.key),
      };
    });
  };

  //  SHORT answer keyword management 

  const handleKeywordChange = (index, value) => {
    setQuestionForm((prev) => {
      const nextKeywords = [...prev.keywords];
      nextKeywords[index] = value;
      return { ...prev, keywords: nextKeywords };
    });
  };

  const addKeyword = () => {
    setQuestionForm((prev) => ({
      ...prev,
      keywords: [...prev.keywords, ""],
    }));
  };

  const removeKeyword = (index) => {
    setQuestionForm((prev) => {
      if (prev.keywords.length <= 1) {
        return prev;
      }

      return {
        ...prev,
        keywords: prev.keywords.filter((_, keywordIndex) => keywordIndex !== index),
      };
    });
  };

  // ─── MULTI_MCQ answer selection ─────────────────────────────────────────

  // Toggles an option key in the multi-answer selection array.
  const toggleMultiAnswer = (optionKey) => {
    setQuestionForm((prev) => {
      const exists = prev.answers.includes(optionKey);
      return {
        ...prev,
        answers: exists
          ? prev.answers.filter((key) => key !== optionKey)
          : [...prev.answers, optionKey],
      };
    });
  };

  // ─── Table display helpers ───────────────────────────────────────────────

  // Formats an answer value for the "Answer" column (handles arrays, objects, and primitives).
  const getAnswerDisplay = (answer) => {
    if (Array.isArray(answer)) {
      return answer.join(", ");
    }

    if (answer && typeof answer === "object") {
      return answer.correct || JSON.stringify(answer);
    }

    return answer ?? "";
  };

  // ─── Edit: question → form state mapping ────────────────────────────────

  // Converts a API question object into the shape expected by the drawer form.
  // Handles varied option formats (array vs object), normalises answers, and
  // converts numeric values to strings for controlled inputs.
  const mapQuestionToFormState = (question) => {
    const normalizeOptions = (value) => {
      if (!value) return {};

      if (Array.isArray(value)) {
        return value.reduce((accumulator, option, index) => {
          if (option && typeof option === "object") {
            const key = String(option.key ?? String.fromCharCode(65 + index)).trim();
            const optionValue = option.value ?? option.text ?? "";
            if (key) {
              accumulator[key] = String(optionValue);
            }
            return accumulator;
          }

          const key = String.fromCharCode(65 + index);
          accumulator[key] = String(option ?? "");
          return accumulator;
        }, {});
      }

      if (typeof value === "object") {
        return Object.entries(value).reduce((accumulator, [key, optionValue]) => {
          const safeKey = String(key).trim();
          if (safeKey) {
            accumulator[safeKey] = String(optionValue ?? "");
          }
          return accumulator;
        }, {});
      }

      return {};
    };

    const optionsObj = normalizeOptions(question?.options);
    const optionEntries = Object.entries(optionsObj);
    const mappedOptions = optionEntries.length
      ? optionEntries
          .sort(([first], [second]) => first.localeCompare(second))
          .map(([key, value]) => ({ key, value: String(value ?? "") }))
      : [
          { key: "A", value: "" },
          { key: "B", value: "" },
        ];

    const rawAnswer = question?.answer;
    const normalizedAnswer = rawAnswer && typeof rawAnswer === "object" && !Array.isArray(rawAnswer)
      ? (rawAnswer.correct ?? rawAnswer.answer ?? rawAnswer.value ?? "")
      : rawAnswer;
    const isMultiMcq = question?.type === "MULTI_MCQ";
    const isNumeric = question?.type === "NUMERIC";

    const normalizedMultiAnswers = (() => {
      if (!isMultiMcq) return [];
      if (Array.isArray(normalizedAnswer)) return normalizedAnswer.map((item) => String(item));
      if (typeof normalizedAnswer === "string") {
        return normalizedAnswer
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      }
      return normalizedAnswer ? [String(normalizedAnswer)] : [];
    })();

    const normalizedKeywords = Array.isArray(question?.keywords)
      ? question.keywords.map((keyword) => String(keyword ?? ""))
      : typeof question?.keywords === "string"
        ? question.keywords.split(",").map((keyword) => keyword.trim()).filter(Boolean)
        : [];

    const normalizedDifficulty = Number(question?.difficulty);
    const difficultyValue = Number.isFinite(normalizedDifficulty) && normalizedDifficulty > 0
      ? String(Math.trunc(normalizedDifficulty))
      : "1";

    const toleranceValue = Number(question?.tolerance);

    return {
      topic_id: question?.topic_id != null ? String(question.topic_id) : "",
      text: question?.text ?? "",
      type: question?.type ?? "",
      options: mappedOptions,
      answer: isMultiMcq
        ? ""
        : normalizedAnswer == null
          ? ""
          : String(normalizedAnswer),
      answers: normalizedMultiAnswers,
      difficulty: difficultyValue,
      tolerance: isNumeric && question?.tolerance != null
        ? (Number.isFinite(toleranceValue) ? String(toleranceValue) : "")
        : "",
      keywords: normalizedKeywords.length
        ? normalizedKeywords
        : [""],
      image_url: question?.image_url ?? "",
      imageUploading: false,
    };
  };

  // ─── Form state → API payload ────────────────────────────────────────────

  // Converts the drawer form state into the shape expected by the backend.
  // Only includes fields relevant to the selected question type.
  const buildPayload = () => {
    const payload = {
      topic_id: Number(questionForm.topic_id),
      text: questionForm.text,
      type: questionForm.type,
      difficulty: questionForm.difficulty === "" ? undefined : Number(questionForm.difficulty),
    };

    if (["MCQ", "MULTI_MCQ"].includes(questionForm.type)) {
      payload.options = questionForm.options.reduce((accumulator, option) => {
        if (option.key.trim()) {
          accumulator[option.key.trim()] = option.value;
        }
        return accumulator;
      }, {});
    }

    if (questionForm.type === "MCQ") {
      payload.answer = questionForm.answer;
    }

    if (questionForm.type === "MULTI_MCQ") {
      payload.answer = questionForm.answers;
    }

    if (["NUMERIC", "SHORT", "OPEN"].includes(questionForm.type)) {
      payload.answer = questionForm.answer;
    }

    if (questionForm.type === "NUMERIC") {
      payload.answer = questionForm.answer === "" ? undefined : Number(questionForm.answer);
      payload.tolerance = questionForm.tolerance === "" ? undefined : Number(questionForm.tolerance);
    }

    if (questionForm.type === "SHORT") {
      payload.keywords = questionForm.keywords;
    }

    payload.image_url = questionForm.image_url || null;

    return payload;
  };

  // ─── Create / Edit submission ────────────────────────────────────────────

  // Submits the drawer form. Uses POST for new questions and PUT for edits.
  // On success, refreshes the question list and closes the drawer.
  const handleCreateQuestion = async () => {
    setSubmitting(true);
    setFormError("");
    setFormSuccess("");

    try {
      if (!/^\d+$/.test(questionForm.difficulty)) {
        throw new Error("Difficulty must be an integer.");
      }

      if (latexIssues.hasAnyIssues) {
        throw new Error("Fix LaTeX delimiter issues before saving.");
      }

      const isEditing = editingQuestionId !== null;
      const url = isEditing
        ? `${API_URL}/questions/${editingQuestionId}`
        : `${API_URL}/questions/create`;

      const res = await fetch(url, {
        method: isEditing ? "PUT" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(buildPayload()),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create question");
      }

      await refreshQuestions();
      setDrawerOpen(false);
      setEditingQuestionId(null);
      setQuestionForm(createInitialFormState());
      setFormSuccess(editingQuestionId !== null ? "Question updated successfully." : "Question created successfully.");
    } catch (err) {
      console.error(err);
      setFormError(err.message || (editingQuestionId !== null ? "Failed to update question" : "Failed to create question"));
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Row selection ─────────────────────────────────────────────────────

  // Toggles a single row in the selected IDs set.
  const toggleQuestionSelection = (questionId) => {
    setSelectedQuestionIds((prev) =>
      prev.includes(questionId)
        ? prev.filter((id) => id !== questionId)
        : [...prev, questionId]
    );
  };

  // Selects / deselects all rows on the current page.
  const togglePageSelection = () => {
    const pageIds = paginatedFiltered.map((q) => q.id);
    const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedQuestionIds.includes(id));

    if (allSelected) {
      setSelectedQuestionIds((prev) => prev.filter((id) => !pageIds.includes(id)));
      return;
    }

    setSelectedQuestionIds((prev) => [...new Set([...prev, ...pageIds])]);
  };

  // ─── Delete handlers ──────────────────────────────────────────────────

  // Deletes a single question after confirmation.
  const handleDeleteQuestion = async (questionId) => {
    if (!window.confirm("Delete this question?")) {
      return;
    }

    setDeleting(true);
    setFormError("");
    setFormSuccess("");

    try {
      const res = await fetch(`${API_URL}/questions/${questionId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete question");
      }

      await refreshQuestions();
      setFormSuccess(data.message || "Question deleted successfully.");
    } catch (err) {
      console.error(err);
      setFormError(err.message || "Failed to delete question");
    } finally {
      setDeleting(false);
    }
  };

  // Populates the drawer with an existing question's data for editing.
  const handleEditQuestion = (questionId) => {
    const questionToEdit = questions.find((q) => q.id === questionId);
    if (!questionToEdit) {
      setFormError("Question not found for editing.");
      return;
    }

    setEditingQuestionId(questionId);
    setQuestionForm(mapQuestionToFormState(questionToEdit));
    setFormError("");
    setFormSuccess("");
    setDrawerOpen(true);
  };

  // Deletes all currently selected questions in a single bulk request.
  const handleDeleteSelected = async () => {
    if (!selectedQuestionIds.length) {
      setFormError("Select at least one question to delete.");
      return;
    }

    if (!window.confirm(`Delete ${selectedQuestionIds.length} selected question(s)?`)) {
      return;
    }

    setDeleting(true);
    setFormError("");
    setFormSuccess("");

    try {
      const res = await fetch(`${API_URL}/questions`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ids: selectedQuestionIds }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete selected questions");
      }

      await refreshQuestions();
      setFormSuccess(data.message || "Selected questions deleted.");
    } catch (err) {
      console.error(err);
      setFormError(err.message || "Failed to delete selected questions");
    } finally {
      setDeleting(false);
    }
  };

  // Deletes every question owned by this user. Requires confirmation.
  const handleDeleteAllQuestions = async () => {
    if (!window.confirm("Delete ALL questions? This cannot be undone.")) {
      return;
    }

    setDeleting(true);
    setFormError("");
    setFormSuccess("");

    try {
      const res = await fetch(`${API_URL}/questions/all/confirm`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete all questions");
      }

      await refreshQuestions();
      setFormSuccess(data.message || "All questions deleted.");
    } catch (err) {
      console.error(err);
      setFormError(err.message || "Failed to delete all questions");
    } finally {
      setDeleting(false);
    }
  };

  // ─── AI generation handlers ──────────────────────────────────────────────

  const resetAiDialog = () => {
    setAiStep(1);
    setAiFile(null);
    setAiTopicId("");
    setAiDefaultTopicId("");
    setAiSuggestedTopics([]);
    setAiSuggestedNewTopicNames([]);
    setAiReviewTopicName("");
    setAiReviewTopicError("");
    setAiCreatingReviewTopic(false);
    setAiSelectedTypes(new Set());
    setAiDifficultyDistribution({ 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 });
    setAiError("");
    setAiGeneratedQuestions([]);
    setAiWarnings([]);
    setAiSaveError("");
    setAiFileFeasibility(null);
    setAiFeasibilityLoading(false);
    setAiEditingKey(null);
    setAiProgress({ stage: "", percent: 0 });
  };

  // Asks the backend AI to score how well each question type fits the uploaded document.
  const analyzeFeasibility = async (file) => {
    if (!file) { setAiFileFeasibility(null); return; }
    if (!API_URL) {
      setAiFileFeasibility(null);
      setAiError("REACT_APP_API_URL is not configured.");
      return;
    }
    setAiFeasibilityLoading(true);
    setAiFileFeasibility(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/ai/feasibility`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Feasibility check failed");
      setAiFileFeasibility({ scores: data.scores });
    } catch (err) {
      // Non-blocking: show the error but still allow question generation.
      setAiFileFeasibility(null);
      const message = err instanceof Error ? err.message : "Feasibility check failed";
      setAiError(message);
    } finally {
      setAiFeasibilityLoading(false);
    }
  };

  // Patches a single generated question in the review list.
  const updateAiQuestion = (key, patch) => {
    setAiGeneratedQuestions((prev) =>
      prev.map((q) => (q._key === key ? { ...q, ...patch } : q))
    );
  };

  const applyDefaultTopicToUnassigned = () => {
    if (!aiDefaultTopicId) return;
    const defaultId = Number(aiDefaultTopicId);
    setAiGeneratedQuestions((prev) =>
      prev.map((q) => (q.topic_id ? q : { ...q, topic_id: defaultId }))
    );
  };

  const handleCreateTopicInAiReview = async (nameOverride = null) => {
    const rawName = typeof nameOverride === "string" ? nameOverride : aiReviewTopicName;
    const name = String(rawName || "").trim();
    if (!name) {
      setAiReviewTopicError("Topic name cannot be empty");
      return;
    }

    setAiCreatingReviewTopic(true);
    setAiReviewTopicError("");
    try {
      const res = await fetch(`${API_URL}/topics`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create topic");

      const topicData = await fetchTopics();
      setTopics(topicData);

      const newTopicId = String(data.id);
      setAiDefaultTopicId(newTopicId);
      setAiTopicId(newTopicId);
      setAiSuggestedTopics((prev) => {
        const withoutDup = prev.filter((t) => String(t.topic_id) !== newTopicId);
        return [{ topic_id: data.id, topic_name: data.name, confidence: 1, source: "created" }, ...withoutDup];
      });
      setAiSuggestedNewTopicNames((prev) => prev.filter((n) => n.toLowerCase() !== name.toLowerCase()));
      setAiReviewTopicName("");
    } catch (err) {
      setAiReviewTopicError(err.message || "Failed to create topic");
    } finally {
      setAiCreatingReviewTopic(false);
    }
  };

  const handleAiGenerate = async () => {
    if (!aiFile || aiSelectedTypes.size === 0) {
      setAiError("Please select a file and at least one question type.");
      return;
    }

    const totalCount = Object.values(aiDifficultyDistribution).reduce((a, b) => a + b, 0);
    if (totalCount === 0) {
      setAiError("Please select at least one question to generate.");
      return;
    }

    if (!hasCompatibleGenerationPlan) {
      setAiError(
        "Selected question types are incompatible with the chosen difficulty levels. Adjust types or difficulty counts to continue."
      );
      return;
    }

    setAiGenerating(true);
    setAiError("");
    setAiProgress({ stage: "Preparing requests...", percent: 5 });
    try {
      const requests = [];
      let globalKeyCounter = 0;
      const activeDifficulties = Object.entries(aiDifficultyDistribution).filter(([, c]) => c > 0);
      const totalBatches = activeDifficulties.length;

      for (const [difficulty, count] of activeDifficulties) {
          const formData = new FormData();
          formData.append("file", aiFile);
          if (aiTopicId) {
            formData.append("topic_id", aiTopicId);
          }
          formData.append(
            "question_types",
            QUESTION_TYPES.filter((type) => aiSelectedTypes.has(type)).join(",")
          );
          formData.append("difficulty", difficulty);
          formData.append("count", String(count));

          // Capture current counter value for this request
          const counterAtThisRequest = globalKeyCounter;
          globalKeyCounter += count;

          requests.push(
            (async () => {
              try {
                const res = await fetch(`${API_URL}/ai/generate-questions`, {
                  method: "POST",
                  headers: { Authorization: `Bearer ${token}` },
                  body: formData,
                });
                const data = await res.json();
                if (!res.ok || data.detail) {
                  throw new Error(data.detail || "Generation failed");
                }
                return {
                  generated: (data.generated || []).map((q, idx) => ({
                    ...q,
                    _key: counterAtThisRequest + idx,
                    topic_id: q.topic_id ?? null,
                  })),
                  warnings: data.validation_warnings || [],
                  suggestedTopics: data.suggested_topics || [],
                  suggestedNewTopicNames: data.suggested_new_topic_names || [],
                };
              } finally {
                setAiProgress((prev) => {
                  const previousUnits = Math.max(
                    0,
                    Math.min(
                      totalBatches,
                      Math.round(((prev.percent - 5) / 90) * totalBatches)
                    )
                  );
                  const nextUnits = Math.min(totalBatches, previousUnits + 1);
                  const percent = Math.min(95, Math.round((nextUnits / totalBatches) * 90) + 5);
                  return {
                    stage: nextUnits < totalBatches ? "Generating questions..." : "Validating output...",
                    percent,
                  };
                });
              }
            })()
          );
      }

      const results = await Promise.all(requests);

      // Merge all results
      const mergedQuestions = results.flatMap((r) => r.generated);
      const mergedWarnings = results.flatMap((r) => r.warnings);
      const mergedSuggestions = results
        .flatMap((r) => r.suggestedTopics || [])
        .filter((s) => s && s.topic_id != null)
        .reduce((acc, item) => {
          const key = String(item.topic_id);
          const existing = acc.get(key);
          if (!existing || (item.confidence || 0) > (existing.confidence || 0)) {
            acc.set(key, item);
          }
          return acc;
        }, new Map());

      const rankedSuggestions = [...mergedSuggestions.values()]
        .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
        .slice(0, 3);

      const seenNewNames = new Set();
      const mergedNewTopicNames = results
        .flatMap((r) => r.suggestedNewTopicNames || [])
        .filter((n) => {
          if (typeof n !== "string" || !n.trim()) return false;
          const lower = n.trim().toLowerCase();
          if (seenNewNames.has(lower)) return false;
          seenNewNames.add(lower);
          return true;
        })
        .map((n) => n.trim())
        .slice(0, 5);

      const preferredTopic = String(
        aiDefaultTopicId
        ?? aiTopicId
        ?? rankedSuggestions[0]?.topic_id
        ?? ""
      );

      const withTopicDefaults = mergedQuestions.map((q) => ({
        ...q,
        topic_id: q.topic_id ?? (preferredTopic ? Number(preferredTopic) : null),
      }));

      if (withTopicDefaults.length === 0) {
        throw new Error("No questions were generated. Please try again.");
      }

      setAiGeneratedQuestions(withTopicDefaults);
      setAiWarnings(mergedWarnings);
      setAiSuggestedTopics(rankedSuggestions);
      setAiSuggestedNewTopicNames(mergedNewTopicNames);
      setAiDefaultTopicId(preferredTopic);
      setAiStep(2);
      setAiProgress({ stage: "Done", percent: 100 });
    } catch (err) {
      setAiError(err.message || "Generation failed");
    } finally {
      setAiGenerating(false);
    }
  };

  const handleAiDiscardQuestion = (key) => {
    setAiGeneratedQuestions((prev) => prev.filter((q) => q._key !== key));
  };

  const handleAiSaveAll = async () => {
    if (!aiGeneratedQuestions.length) return;
    setAiSaving(true);
    setAiSaveError("");
    try {
      const unassigned = aiGeneratedQuestions.filter((q) => q.topic_id == null || q.topic_id === "");
      if (unassigned.length > 0) {
        throw new Error("Assign a topic to every generated question before saving.");
      }

      for (const q of aiGeneratedQuestions) {
        const { _key, ...payload } = q;
        payload.topic_id = Number(payload.topic_id);
        const res = await fetch(`${API_URL}/questions/create`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const d = await res.json();
          throw new Error(d.detail || "Failed to save question");
        }
      }

      await refreshQuestions();
      setAiDialogOpen(false);
      resetAiDialog();
      setFormSuccess(`${aiGeneratedQuestions.length} question(s) generated and saved.`);
    } catch (err) {
      setAiSaveError(err.message || "Failed to save questions");
    } finally {
      setAiSaving(false);
    }
  };

  // ─── Derived / computed state ────────────────────────────────────────────

  // Applies search text, topic filter, and sort to the full question list.
  const filtered = questions
    .filter((q) =>
      q.text.toLowerCase().includes(search.toLowerCase())
    )
    .filter((q) =>
      topicFilter ? q.topic_name === topicFilter : true
    )
    .sort((a, b) => {
      let diff = 0;
      if (sortBy === "difficulty") diff = a.difficulty - b.difficulty;
      if (sortBy === "due") {
        const aDue = parseDueDate(a.due);
        const bDue = parseDueDate(b.due);
        const aTime = aDue ? aDue.getTime() : Number.POSITIVE_INFINITY;
        const bTime = bDue ? bDue.getTime() : Number.POSITIVE_INFINITY;
        diff = aTime - bTime;
      }
      return sortOrder === "desc" ? -diff : diff;
    });

  // Slices the filtered list to the current page.
  const paginatedFiltered = filtered.slice((page - 1) * perPage, page * perPage);

  // Used by the page-level select-all checkbox.
  const pageIds = paginatedFiltered.map((q) => q.id);
  const isPageSelectionChecked = pageIds.length > 0 && pageIds.every((id) => selectedQuestionIds.includes(id));
  const isPageSelectionIndeterminate = pageIds.some((id) => selectedQuestionIds.includes(id)) && !isPageSelectionChecked;

  // Unique topic names extracted from the loaded questions, used to populate the topic filter dropdown.
  const uniqueTopics = [...new Set(questions.map(q => q.topic_name))];

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
    <Box sx={{ p: 4 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1, flexWrap: "wrap", gap: 1 }}>
        <Typography variant="h4" gutterBottom sx={{ mb: 0 }}>
          Question Database
        </Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button variant="outlined" onClick={() => navigate(-1)}>
            Back
          </Button>
          <Button variant="outlined" onClick={() => navigate("/home")}>
            Home
          </Button>
        </Box>
      </Box>

      {/* 🔍 Search */}
      <TextField
        fullWidth
        label="Search Questions"
        sx={{ mb: 2 }}
        value={search}
        onChange={(e) => {setSearch(e.target.value); setPage(1);}}
      />

      {/* 🎯 Filters */}
      <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>Topic</InputLabel>
          <Select
            value={topicFilter}
            onChange={(e) => {
              setTopicFilter(e.target.value);
              setPage(1);
            }}
          >
            <MenuItem value="">All</MenuItem>
            {uniqueTopics.map((t) => (
              <MenuItem key={t} value={t}>{t}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Box sx={{ display: "flex", gap: 1 }}>
          <FormControl sx={{ minWidth: 150 }}>
            <InputLabel>Sort</InputLabel>
            <Select
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
            >
              <MenuItem value="">None</MenuItem>
              <MenuItem value="difficulty">Difficulty</MenuItem>
              <MenuItem value="due">Next Review</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="outlined"
            onClick={() => { setSortOrder(sortOrder === "asc" ? "desc" : "asc"); setPage(1); }}
            sx={{ minWidth: 80, height: FILTER_CONTROL_HEIGHT }}
          >
            {sortOrder.toUpperCase()}
          </Button>
        </Box>

        <FormControl sx={{ minWidth: 120 }}>
          <InputLabel>Per Page</InputLabel>
          <Select
            value={perPage}
            onChange={(e) => {
              setPerPage(e.target.value);
              setPage(1); // Reset to first page
            }}
          >
            <MenuItem value={5}>5</MenuItem>
            <MenuItem value={10}>10</MenuItem>
            <MenuItem value={25}>25</MenuItem>
            <MenuItem value={50}>50</MenuItem>
          </Select>
        </FormControl>

        <Button
          variant="contained"
          onClick={() => setShowAnswers(!showAnswers)}
          color="secondary"
          sx={{ height: FILTER_CONTROL_HEIGHT }}
        >
          {showAnswers ? "Hide Answers" : "Show Answers"}
        </Button>

        <Box sx={{ ml: "auto", display: "flex", gap: 1, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <Button
            variant="outlined"
            color="error"
            onClick={handleDeleteSelected}
            disabled={deleting || selectedQuestionIds.length === 0}
            sx={{ height: FILTER_CONTROL_HEIGHT }}
          >
            Delete Selected ({selectedQuestionIds.length})
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleDeleteAllQuestions}
            disabled={deleting || questions.length === 0}
            sx={{ height: FILTER_CONTROL_HEIGHT }}
          >
            Delete All
          </Button>
          <Button
            variant="contained"
            onClick={() => {
              setEditingQuestionId(null);
              setQuestionForm(createInitialFormState());
              setDrawerOpen(true);
              setFormError("");
              setFormSuccess("");
            }}
            sx={{ height: FILTER_CONTROL_HEIGHT }}
            disabled={deleting}
          >
            Create New Question
          </Button>
          <Button
            variant="outlined"
            color="secondary"
            onClick={() => { resetAiDialog(); setAiDialogOpen(true); }}
            sx={{ height: FILTER_CONTROL_HEIGHT }}
            disabled={deleting}
          >
            Generate with AI
          </Button>
        </Box>
      </Box>

      {formError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {formError}
        </Alert>
      ) : null}

      {formSuccess ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          {formSuccess}
        </Alert>
      ) : null}

      <Box sx={{ display: "flex", gap: 3, mb: 3 }}>
        <Typography>Total: {questions.length}</Typography>
        <Typography>
            Due: {questions.filter((q) => isDueNow(q.due)).length}
        </Typography>
        <Typography>
            New: {questions.filter((q) => !parseDueDate(q.due)).length}
        </Typography>
      </Box>

      {/* 📊 Table */}
      <TableContainer component={Paper}>
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  checked={isPageSelectionChecked}
                  indeterminate={isPageSelectionIndeterminate}
                  onChange={togglePageSelection}
                />
              </TableCell>
              <TableCell>Question</TableCell>
              <TableCell>Topic</TableCell>
              <TableCell>Difficulty</TableCell>
              <TableCell>Next Review</TableCell>
              {showAnswers && <TableCell>Options</TableCell>}
              {showAnswers && <TableCell>Answer</TableCell>}
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {paginatedFiltered.map((q) => (
              <TableRow key={q.id}>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selectedQuestionIds.includes(q.id)}
                    onChange={() => toggleQuestionSelection(q.id)}
                  />
                </TableCell>
                <TableCell component="div"><MathText text={q.text} /></TableCell>
                <TableCell>{q.topic_name}</TableCell>
                <TableCell>{q.difficulty}</TableCell>
                <TableCell>
                  {!parseDueDate(q.due) ? (
                    "New"
                  ) : isDueNow(q.due) ? (
                    <Typography color="error">Due Now</Typography>
                  ) : (
                    parseDueDate(q.due).toLocaleString()
                  )}
                </TableCell>
                {showAnswers && (
                  <TableCell>
                    {q.options ? Object.entries(q.options).map(([key, value]) => `${key}: ${value}`).join(', ') : ''}
                  </TableCell>
                )}
                {showAnswers && (
                  <TableCell>
                    {getAnswerDisplay(q.answer)}
                  </TableCell>
                )}
                <TableCell>
                  <Button
                    variant="text"
                    color="error"
                    onClick={() => handleDeleteQuestion(q.id)}
                    disabled={deleting}
                  >
                    Delete
                  </Button>
                  <Button
                    variant="text"
                    color="primary"
                    onClick={() => handleEditQuestion(q.id)}
                    disabled={deleting}
                  >
                    Edit
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 📄 Pagination */}
      <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
        <Pagination
          count={Math.ceil(filtered.length / perPage)}
          page={page}
          onChange={(event, value) => setPage(value)}
          color="primary"
        />
      </Box>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={() => {
          if (!submitting) {
            setDrawerOpen(false);
          }
        }}
      >
        <Box sx={{ width: { xs: 360, sm: 480 }, p: 3 }}>
          <Typography variant="h5" gutterBottom>
            {editingQuestionId !== null ? "Edit Question" : "Create New Question"}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {editingQuestionId !== null
              ? "Update the question details and save your changes."
              : "Fill in the question details. Additional fields appear after you choose a question type."}
          </Typography>

          {formError ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {formError}
            </Alert>
          ) : null}

          <Stack spacing={2}>
            <FormControl fullWidth>
              <InputLabel>Question Type</InputLabel>
              <Select
                value={questionForm.type}
                label="Question Type"
                onChange={(e) => handleTypeChange(e.target.value)}
              >
                {QUESTION_TYPES.map((type) => (
                  <MenuItem key={type} value={type}>{type}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth>
              <InputLabel>Topic</InputLabel>
              <Select
                value={questionForm.topic_id}
                label="Topic"
                onChange={(e) => updateQuestionForm("topic_id", e.target.value)}
              >
                {topics.map((topic) => (
                  <MenuItem key={topic.id} value={topic.id}>{topic.name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
              <TextField
                label="New Topic Name"
                size="small"
                fullWidth
                value={newTopicName}
                onChange={(e) => { setNewTopicName(e.target.value); setNewTopicError(""); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleCreateTopic(); } }}
                error={Boolean(newTopicError)}
                helperText={newTopicError || " "}
              />
              <Button
                variant="outlined"
                onClick={handleCreateTopic}
                disabled={creatingTopic || !newTopicName.trim()}
                sx={{ mt: 0.5, whiteSpace: "nowrap" }}
              >
                {creatingTopic ? "Adding..." : "Add Topic"}
              </Button>
            </Box>

            <TextField
              label="Question Text"
              fullWidth
              multiline
              minRows={3}
              value={questionForm.text}
              onChange={(e) => updateQuestionForm("text", e.target.value)}
              error={latexIssues.textIssues.length > 0}
              helperText={latexIssues.textIssues[0] || "Use \\( ... \\) for inline and \\[ ... \\] for block math."}
            />

            {questionForm.text?.trim() && (
              <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.paper" }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Preview
                </Typography>
                <Typography variant="body2" component="div">
                  <MathText text={questionForm.text} />
                </Typography>
              </Box>
            )}

            {questionForm.type ? (
              <>
                {["MCQ", "MULTI_MCQ"].includes(questionForm.type) ? (
                  <>
                    <Divider />
                    <Typography variant="subtitle1">Options</Typography>
                    {questionForm.options.map((option, index) => (
                      <Box key={`${index}-${option.key}`} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                        <TextField
                          label="Key"
                          value={option.key}
                          onChange={(e) => handleOptionChange(index, "key", e.target.value)}
                          sx={{ width: 100 }}
                        />
                        <TextField
                          label="Value"
                          value={option.value}
                          onChange={(e) => handleOptionChange(index, "value", e.target.value)}
                          fullWidth
                          error={latexIssues.optionIssues[index]?.length > 0}
                          helperText={latexIssues.optionIssues[index]?.[0] || " "}
                        />
                        <Button
                          variant="text"
                          color="error"
                          onClick={() => removeOption(index)}
                          disabled={questionForm.options.length <= 2}
                        >
                          Remove
                        </Button>
                      </Box>
                    ))}
                    <Button variant="outlined" onClick={addOption}>
                      Add Option
                    </Button>

                    {questionForm.options.some((option) => option.value?.trim()) && (
                      <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.paper" }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                          Options Preview
                        </Typography>
                        {questionForm.options.map((option) => (
                          <Typography key={`preview-${option.key}`} variant="body2" component="div" sx={{ mb: 0.25 }}>
                            <strong>{option.key || "?"}:</strong> <MathText text={option.value} />
                          </Typography>
                        ))}
                      </Box>
                    )}
                  </>
                ) : null}

                {questionForm.type === "MCQ" ? (
                  <FormControl fullWidth>
                    <InputLabel>Answer</InputLabel>
                    <Select
                      value={questionForm.answer}
                      label="Answer"
                      onChange={(e) => updateQuestionForm("answer", e.target.value)}
                    >
                      {questionForm.options.map((option) => (
                        <MenuItem key={option.key} value={option.key}>
                          {option.key || "Untitled"}: {option.value || "No value"}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : null}

                {questionForm.type === "MULTI_MCQ" ? (
                  <Box>
                    <Typography variant="subtitle1" sx={{ mb: 1 }}>
                      Correct Answers
                    </Typography>
                    {questionForm.options.map((option) => (
                      <FormControlLabel
                        key={option.key}
                        control={
                          <Checkbox
                            checked={questionForm.answers.includes(option.key)}
                            onChange={() => toggleMultiAnswer(option.key)}
                          />
                        }
                        label={`${option.key || "Untitled"}: ${option.value || "No value"}`}
                      />
                    ))}
                  </Box>
                ) : null}

                {["NUMERIC", "SHORT", "OPEN"].includes(questionForm.type) ? (
                  <TextField
                    label="Answer"
                    type={questionForm.type === "NUMERIC" ? "number" : "text"}
                    fullWidth
                    multiline={questionForm.type !== "NUMERIC"}
                    minRows={questionForm.type === "NUMERIC" ? undefined : 2}
                    value={questionForm.answer}
                    onChange={(e) => updateQuestionForm("answer", e.target.value)}
                    error={["SHORT", "OPEN"].includes(questionForm.type) && latexIssues.answerIssues.length > 0}
                    helperText={
                      ["SHORT", "OPEN"].includes(questionForm.type)
                        ? (latexIssues.answerIssues[0] || "Use \\( ... \\) for inline and \\[ ... \\] for block math.")
                        : undefined
                    }
                  />
                ) : null}

                {["SHORT", "OPEN"].includes(questionForm.type) && questionForm.answer?.trim() && (
                  <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.paper" }}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                      Answer Preview
                    </Typography>
                    <Typography variant="body2" component="div">
                      <MathText text={questionForm.answer} />
                    </Typography>
                  </Box>
                )}

                <TextField
                  label="Difficulty"
                  type="number"
                  fullWidth
                  value={questionForm.difficulty}
                  onChange={(e) => handleDifficultyChange(e.target.value)}
                  inputProps={{ step: 1, min: 1 }}
                />

                {questionForm.type === "NUMERIC" ? (
                  <TextField
                    label="Tolerance"
                    type="number"
                    fullWidth
                    value={questionForm.tolerance}
                    onChange={(e) => updateQuestionForm("tolerance", e.target.value)}
                  />
                ) : null}

                {questionForm.type === "SHORT" ? (
                  <>
                    <Divider />
                    <Typography variant="subtitle1">Keywords</Typography>
                    {questionForm.keywords.map((keyword, index) => (
                      <Box key={`${index}-${keyword}`} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                        <TextField
                          label={`Keyword ${index + 1}`}
                          value={keyword}
                          onChange={(e) => handleKeywordChange(index, e.target.value)}
                          fullWidth
                        />
                        <Button
                          variant="text"
                          color="error"
                          onClick={() => removeKeyword(index)}
                          disabled={questionForm.keywords.length <= 1}
                        >
                          Remove
                        </Button>
                      </Box>
                    ))}
                    <Button variant="outlined" onClick={addKeyword}>
                      Add Keyword
                    </Button>
                  </>
                ) : null}
              </>
            ) : null}

            {/* ─── Image upload ─────────────────────────────────────────── */}
            <Box>
              <Button
                variant="outlined"
                component="label"
                disabled={questionForm.imageUploading}
                size="small"
              >
                {questionForm.imageUploading ? "Uploading…" : "Attach Image"}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleImageUpload(file);
                    e.target.value = "";
                  }}
                />
              </Button>

              {questionForm.image_url && (
                <Box sx={{ mt: 1 }}>
                  <img
                    src={questionForm.image_url}
                    alt="Question preview"
                    style={{ maxWidth: "100%", maxHeight: 180, borderRadius: 4, display: "block" }}
                  />
                  <Button
                    size="small"
                    color="error"
                    sx={{ mt: 0.5 }}
                    onClick={() => updateQuestionForm("image_url", "")}
                  >
                    Remove image
                  </Button>
                </Box>
              )}
            </Box>

            <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, pt: 1 }}>
              <Button
                variant="text"
                onClick={() => {
                  setDrawerOpen(false);
                  setEditingQuestionId(null);
                }}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                variant="contained"
                onClick={handleCreateQuestion}
                disabled={submitting || questionForm.imageUploading}
              >
                {submitting
                  ? (editingQuestionId !== null ? "Saving..." : "Creating...")
                  : (editingQuestionId !== null ? "Save Changes" : "Create Question")}
              </Button>
            </Box>
          </Stack>
        </Box>
      </Drawer>
      <Dialog
        open={aiDialogOpen}
        onClose={() => { if (!aiGenerating && !aiSaving) { setAiDialogOpen(false); resetAiDialog(); } }}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { minHeight: 400 } }}
      >
        <DialogTitle>
          {aiStep === 1 ? "Generate Questions with AI" : `Review Generated Questions (${aiGeneratedQuestions.length})`}
        </DialogTitle>

        <DialogContent dividers>
          {/* ── Step 1: Upload form ── */}
          {aiStep === 1 && (
            <Stack spacing={3} sx={{ pt: 1 }}>
              {aiError && <Alert severity="error">{aiError}</Alert>}

              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Upload a PDF, text file, or image and the AI will generate questions from its content.
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                  <Button variant="outlined" component="label" disabled={aiGenerating}>
                    {aiFile ? aiFile.name : "Choose File"}
                    <input
                      type="file"
                      accept=".pdf,.txt,.jpeg,.jpg,.png,.webp"
                      hidden
                      onChange={(e) => {
                        const f = e.target.files?.[0] || null;
                        setAiFile(f);
                        setAiError("");
                        setAiSuggestedTopics([]);
                        analyzeFeasibility(f);
                        e.target.value = "";
                      }}
                    />
                  </Button>

                  {aiFile && (
                    <IconButton
                      size="small"
                      color="error"
                      aria-label="Remove selected file"
                      onClick={() => {
                        setAiFile(null);
                        setAiFileFeasibility(null);
                        setAiError("");
                        setAiTopicId("");
                        setAiDefaultTopicId("");
                        setAiSuggestedTopics([]);
                      }}
                      disabled={aiGenerating}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  )}
                </Box>
              </Box>

              <FormControl fullWidth>
                <InputLabel>Topic (optional)</InputLabel>
                <Select
                  value={aiTopicId}
                  label="Topic (optional)"
                  onChange={(e) => setAiTopicId(e.target.value)}
                >
                  <MenuItem value="">
                    Decide during review
                  </MenuItem>
                  {topics.map((t) => (
                    <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
                  ))}
                </Select>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                  Leave blank if the document spans multiple topics; you can assign per question in review.
                </Typography>
              </FormControl>

              <FormControl fullWidth>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Question Types
                </Typography>
                <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 1 }}>
                  {QUESTION_TYPES.map((type) => {
                    const rawScore = aiFileFeasibility?.scores?.[type];
                    const feasLabel = rawScore == null
                      ? null
                      : rawScore >= 0.6 ? "good"
                      : rawScore >= 0.3 ? "warn"
                      : "poor";
                    return (
                      <FormControlLabel
                        key={type}
                        control={
                          <Checkbox
                            checked={aiSelectedTypes.has(type)}
                            onChange={(e) => {
                              const newSet = new Set(aiSelectedTypes);
                              if (e.target.checked) {
                                newSet.add(type);
                              } else {
                                newSet.delete(type);
                              }
                              setAiSelectedTypes(newSet);
                            }}
                          />
                        }
                        label={
                          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                            <span>{type}</span>
                            <Tooltip title={TYPE_INFO_MAP[type]} arrow>
                              <InfoOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} />
                            </Tooltip>
                            {aiFeasibilityLoading && (
                              <Typography variant="caption" color="text.disabled">scoring…</Typography>
                            )}
                            {!aiFeasibilityLoading && feasLabel && (
                              <Chip
                                size="small"
                                label={
                                  feasLabel === "good"
                                    ? `✓ ${Math.round(rawScore * 100)}%`
                                    : feasLabel === "warn"
                                    ? `~ ${Math.round(rawScore * 100)}%`
                                    : `✗ ${Math.round(rawScore * 100)}%`
                                }
                                color={feasLabel === "good" ? "success" : feasLabel === "warn" ? "warning" : "error"}
                                sx={{ height: 18, fontSize: "0.6rem", pointerEvents: "none" }}
                              />
                            )}
                          </Box>
                        }
                      />
                    );
                  })}
                </Box>
                {aiFileFeasibility?.scores && (() => {
                  const poorSelected = orderedSelectedTypes.filter(
                    (t) => (aiFileFeasibility.scores[t] ?? 1) < 0.3
                  );
                  return poorSelected.length > 0 ? (
                    <Alert severity="warning" sx={{ mt: 0.5 }}>
                      {poorSelected.join(", ")} score{poorSelected.length > 1 ? "" : "s"} below 30% for this document.
                      The AI may generate low-quality or hallucinated questions for {poorSelected.length > 1 ? "these types" : "this type"}.
                      Consider deselecting {poorSelected.length > 1 ? "them" : "it"} or choosing a different document.
                    </Alert>
                  ) : null;
                })()}
                <Box sx={{ mt: 1 }}>
                  {aiFileFeasibility?.scores && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Scores are AI-assessed suitability from the uploaded document.
                    </Typography>
                  )}

                  <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
                    How are questions distributed?
                  </Typography>

                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.25 }}>
                    Levels 1-2: Mostly MCQ and SHORT answer questions, focused on recall and recognition.
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.25 }}>
                    Level 3: A mixture of all question types.
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Levels 4-5: More MULTI_MCQ and OPEN questions, focused on higher levels of thinking and analysis
                  </Typography>
                </Box>
                <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                  {QUESTION_TYPES.filter((type) => aiSelectedTypes.has(type)).map((type) => (
                    <Chip key={type} size="small" variant="outlined" label={`${type}: ${TYPE_BLOOM_MAP[type]}`} />
                  ))}
                </Box>
              </FormControl>

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Questions per Difficulty (1–5)
                </Typography>
                <Box sx={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 1 }}>
                  {[1, 2, 3, 4, 5].map((diff) => (
                    <TextField
                      key={diff}
                      label={`L${diff}`}
                      type="number"
                      size="small"
                      value={aiDifficultyDistribution[diff] || 0}
                      onChange={(e) => {
                        const newVal = Math.max(0, Math.min(10, parseInt(e.target.value) || 0));
                        setAiDifficultyDistribution((prev) => ({ ...prev, [diff]: newVal }));
                      }}
                      inputProps={{ min: 0, max: 10, step: 1 }}
                    />
                  ))}
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  Total: {Object.values(aiDifficultyDistribution).reduce((a, b) => a + b, 0)} questions
                </Typography>
              </Box>

              {orderedSelectedTypes.length > 0 && plannedTypeSplitByDifficulty.length > 0 && (() => {
                const diffIdx = (level) => Math.max(0, Math.min(4, level - 1));
                const incompatible = orderedSelectedTypes.flatMap((type) =>
                  plannedTypeSplitByDifficulty
                    .filter(({ level }) => TYPE_DIFFICULTY_WEIGHTS[type][diffIdx(level)] === 0)
                    .map(({ level }) => ({ type, level }))
                );
                return (
                  <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Planned Split Preview
                    </Typography>
                    {incompatible.length > 0 && (
                      <Alert severity="warning" sx={{ mb: 1.5 }}>
                        {incompatible.map(({ type, level }) => `${type} at L${level}`).join(", ")} will be
                        excluded - {incompatible.length === 1 ? "this combination is" : "these combinations are"} not
                        compatible with the selected difficulty
                        {incompatible.length === 1 ? " level" : " levels"} (OPEN requires higher order thinking;
                        L1–L2 targets basic recall). Questions will be redistributed across the remaining selected types.
                      </Alert>
                    )}
                    {plannedTypeSplitByDifficulty.map(({ level, requested, split }) => (
                      <Box key={level} sx={{ mb: 1 }}>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                          Difficulty L{level}: {requested} question{requested === 1 ? "" : "s"}
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                          {orderedSelectedTypes
                            .filter((type) => (split[type] || 0) > 0)
                            .map((type) => (
                              <Chip
                                key={`${level}-${type}`}
                                size="small"
                                variant="outlined"
                                label={`${type}: ${split[type]}`}
                              />
                            ))}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                );
              })()}

              {!hasCompatibleGenerationPlan && orderedSelectedTypes.length > 0 && plannedTypeSplitByDifficulty.length > 0 && (
                <Alert severity="error">
                  None of the selected question types can be generated for the chosen difficulty levels.
                  Please change either question types or difficulty distribution.
                </Alert>
              )}

              {aiGenerating && (
                <Box sx={{ mt: 1 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
                    <Typography variant="body2" color="text.secondary">
                      {aiProgress.stage || "Starting..."}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {aiProgress.percent}%
                    </Typography>
                  </Box>
                  <LinearProgress variant="determinate" value={aiProgress.percent} />
                </Box>
              )}
            </Stack>
          )}

          {/* ── Step 2: Review ── */}
          {aiStep === 2 && (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">Topic Assignment</Typography>

                  {aiSuggestedTopics.length > 0 && (
                    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                      {aiSuggestedTopics.map((s) => (
                        <Chip
                          key={`ai-topic-${s.topic_id}`}
                          label={`${s.topic_name} (${Math.round((s.confidence || 0) * 100)}%)`}
                          color={String(s.topic_id) === String(aiDefaultTopicId) ? "primary" : "default"}
                          variant={String(s.topic_id) === String(aiDefaultTopicId) ? "filled" : "outlined"}
                          onClick={() => setAiDefaultTopicId(String(s.topic_id))}
                        />
                      ))}
                    </Box>
                  )}

                  {aiSuggestedNewTopicNames.length > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                        Create suggested topic:
                      </Typography>
                      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                        {aiSuggestedNewTopicNames.map((name) => (
                          <Chip
                            key={`new-topic-${name}`}
                            label={`+ ${name}`}
                            variant="outlined"
                            color="secondary"
                            size="small"
                            onClick={() => handleCreateTopicInAiReview(name)}
                            disabled={aiCreatingReviewTopic}
                          />
                        ))}
                      </Box>
                    </Box>
                  )}

                  <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
                    <FormControl sx={{ minWidth: 260 }} size="small">
                      <InputLabel>Default Topic</InputLabel>
                      <Select
                        value={aiDefaultTopicId}
                        label="Default Topic"
                        onChange={(e) => setAiDefaultTopicId(e.target.value)}
                      >
                        <MenuItem value="">None</MenuItem>
                        {topics.map((t) => (
                          <MenuItem key={`default-topic-${t.id}`} value={String(t.id)}>{t.name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={applyDefaultTopicToUnassigned}
                      disabled={!aiDefaultTopicId}
                    >
                      Apply to unassigned
                    </Button>
                  </Box>

                  <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                    <TextField
                      label="Create new topic"
                      size="small"
                      value={aiReviewTopicName}
                      onChange={(e) => { setAiReviewTopicName(e.target.value); setAiReviewTopicError(""); }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleCreateTopicInAiReview();
                        }
                      }}
                      error={Boolean(aiReviewTopicError)}
                      helperText={aiReviewTopicError || " "}
                    />
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleCreateTopicInAiReview}
                      disabled={aiCreatingReviewTopic || !aiReviewTopicName.trim()}
                    >
                      {aiCreatingReviewTopic ? "Adding..." : "Add"}
                    </Button>
                  </Box>

                </Stack>
              </Paper>

              {aiWarnings.length > 0 && (
                <Alert severity="warning">
                  <Typography variant="body2" fontWeight="bold" sx={{ mb: 0.5 }}>
                    AI output was auto-corrected ({aiWarnings.length} issue{aiWarnings.length > 1 ? "s" : ""}):
                  </Typography>
                  {aiWarnings.map((w, i) => (
                    <Typography key={i} variant="body2">• {w}</Typography>
                  ))}
                </Alert>
              )}

              {aiSaveError && <Alert severity="error">{aiSaveError}</Alert>}

              {aiGeneratedQuestions.length === 0 && (
                <Alert severity="info">All questions have been discarded.</Alert>
              )}

              {aiGeneratedQuestions.map((q) => {
                const isEditing = aiEditingKey === q._key;
                const optionEntries = q.options && typeof q.options === "object" && !Array.isArray(q.options)
                  ? Object.entries(q.options).sort(([a], [b]) => a.localeCompare(b))
                  : [];
                return (
                  <Paper key={q._key} variant="outlined" sx={{ p: 2 }}>
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1 }}>
                      <Box sx={{ flex: 1 }}>
                        <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
                          <Chip label={q.type} size="small" color="primary" variant="outlined" />
                          <Chip label={`Difficulty: ${q.difficulty}`} size="small" variant="outlined" />
                        </Box>

                        <FormControl size="small" sx={{ minWidth: 220, mb: 1.25 }}>
                          <InputLabel>Topic</InputLabel>
                          <Select
                            value={q.topic_id != null ? String(q.topic_id) : ""}
                            label="Topic"
                            onChange={(e) => {
                              const next = e.target.value;
                              updateAiQuestion(q._key, {
                                topic_id: next === "" ? null : Number(next),
                              });
                            }}
                          >
                            <MenuItem value="">Unassigned</MenuItem>
                            {topics.map((topic) => (
                              <MenuItem key={`q-topic-${q._key}-${topic.id}`} value={String(topic.id)}>
                                {topic.name}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>

                        {isEditing ? (
                          <Stack spacing={1.5} sx={{ mt: 1 }}>
                            <TextField
                              label="Question Text"
                              fullWidth
                              multiline
                              minRows={2}
                              size="small"
                              value={q.text}
                              onChange={(e) => updateAiQuestion(q._key, { text: e.target.value })}
                            />

                            {["MCQ", "MULTI_MCQ"].includes(q.type) && optionEntries.length > 0 && (
                              <Box>
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>Options</Typography>
                                {optionEntries.map(([key, val]) => (
                                  <Box key={key} sx={{ display: "flex", gap: 1, mb: 0.5, alignItems: "center" }}>
                                    <Typography variant="body2" sx={{ minWidth: 20 }}>{key}:</Typography>
                                    <TextField
                                      size="small"
                                      fullWidth
                                      value={val}
                                      onChange={(e) =>
                                        updateAiQuestion(q._key, { options: { ...q.options, [key]: e.target.value } })
                                      }
                                    />
                                  </Box>
                                ))}
                              </Box>
                            )}

                            {q.type === "MCQ" && (
                              <FormControl size="small" fullWidth>
                                <InputLabel>Answer</InputLabel>
                                <Select
                                  value={q.answer ?? ""}
                                  label="Answer"
                                  onChange={(e) => updateAiQuestion(q._key, { answer: e.target.value })}
                                >
                                  {optionEntries.map(([key]) => (
                                    <MenuItem key={key} value={key}>{key}</MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            )}

                            {q.type === "MULTI_MCQ" && (
                              <Box>
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>Correct Answers</Typography>
                                {optionEntries.map(([key]) => (
                                  <FormControlLabel
                                    key={key}
                                    control={
                                      <Checkbox
                                        size="small"
                                        checked={Array.isArray(q.answer) && q.answer.includes(key)}
                                        onChange={(e) => {
                                          const current = Array.isArray(q.answer) ? q.answer : [];
                                          updateAiQuestion(q._key, {
                                            answer: e.target.checked
                                              ? [...current, key]
                                              : current.filter((k) => k !== key),
                                          });
                                        }}
                                      />
                                    }
                                    label={key}
                                  />
                                ))}
                              </Box>
                            )}

                            {["NUMERIC", "SHORT", "OPEN"].includes(q.type) && (
                              <TextField
                                label="Answer"
                                fullWidth
                                size="small"
                                type={q.type === "NUMERIC" ? "number" : "text"}
                                multiline={q.type !== "NUMERIC"}
                                minRows={q.type !== "NUMERIC" ? 2 : undefined}
                                value={q.answer ?? ""}
                                onChange={(e) =>
                                  updateAiQuestion(q._key, {
                                    answer: q.type === "NUMERIC"
                                      ? (e.target.value === "" ? "" : Number(e.target.value))
                                      : e.target.value,
                                  })
                                }
                              />
                            )}

                            {q.type === "NUMERIC" && (
                              <TextField
                                label="Tolerance"
                                fullWidth
                                size="small"
                                type="number"
                                value={q.tolerance ?? ""}
                                onChange={(e) =>
                                  updateAiQuestion(q._key, {
                                    tolerance: e.target.value === "" ? undefined : Number(e.target.value),
                                  })
                                }
                              />
                            )}

                            {q.type === "SHORT" && Array.isArray(q.keywords) && (
                              <TextField
                                label="Keywords (comma-separated)"
                                fullWidth
                                size="small"
                                value={q.keywords.join(", ")}
                                onChange={(e) =>
                                  updateAiQuestion(q._key, {
                                    keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean),
                                  })
                                }
                              />
                            )}

                            <TextField
                              label="Explanation"
                              fullWidth
                              multiline
                              minRows={2}
                              size="small"
                              value={q.explanation ?? ""}
                              onChange={(e) => updateAiQuestion(q._key, { explanation: e.target.value })}
                              helperText="Optional: edit the explanation shown with this question."
                            />

                            {/* ── Image upload (edit mode) ── */}
                            <Box>
                              <Button
                                variant="outlined"
                                component="label"
                                size="small"
                                disabled={aiQuestionUploading[q._key]}
                              >
                                {aiQuestionUploading[q._key] ? "Uploading…" : "Attach Image"}
                                <input
                                  type="file"
                                  accept="image/jpeg,image/png,image/webp,image/gif"
                                  hidden
                                  onChange={(e) => {
                                    const f = e.target.files?.[0];
                                    if (f) handleAiQuestionImageUpload(q._key, f);
                                    e.target.value = "";
                                  }}
                                />
                              </Button>
                              {q.image_url && (
                                <Box sx={{ mt: 1 }}>
                                  <img
                                    src={q.image_url}
                                    alt="Question preview"
                                    style={{ maxWidth: "100%", maxHeight: 140, borderRadius: 4, display: "block" }}
                                  />
                                  <Button
                                    size="small"
                                    color="error"
                                    sx={{ mt: 0.5 }}
                                    onClick={() => updateAiQuestion(q._key, { image_url: null })}
                                  >
                                    Remove image
                                  </Button>
                                </Box>
                              )}
                            </Box>
                          </Stack>
                        ) : (
                          <>
                            <Typography variant="body1" component="div" sx={{ mb: 1 }}><MathText text={q.text} /></Typography>

                            {q.options && typeof q.options === "object" && !Array.isArray(q.options) && (
                              <Box sx={{ pl: 1, mb: 1 }}>
                                {Object.entries(q.options).map(([key, val]) => (
                                  <Typography key={key} variant="body2" component="div" color="text.secondary">
                                    {key}: <MathText text={val} />
                                  </Typography>
                                ))}
                              </Box>
                            )}

                            {q.keywords && Array.isArray(q.keywords) && (
                              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                                Keywords: {q.keywords.join(", ")}
                              </Typography>
                            )}

                            <Typography variant="body2" component="div" color="success.main">
                              Answer:{" "}
                              <MathText text={Array.isArray(q.answer) ? q.answer.join(", ") : String(q.answer ?? "")} />
                              {q.tolerance != null && q.type === "NUMERIC" ? ` (±${q.tolerance})` : ""}
                            </Typography>

                            {q.explanation && (
                              <Typography variant="body2" component="div" color="text.secondary" sx={{ mt: 0.5 }}>
                                Explanation: <MathText text={q.explanation} />
                              </Typography>
                            )}

                            {/* ── Image (view mode) ── */}
                            {q.image_url && (
                              <Box sx={{ mt: 1 }}>
                                <img
                                  src={q.image_url}
                                  alt="Question"
                                  style={{ maxWidth: "100%", maxHeight: 140, borderRadius: 4, display: "block" }}
                                />
                              </Box>
                            )}
                          </>
                        )}
                      </Box>

                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, flexShrink: 0 }}>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => setAiEditingKey(isEditing ? null : q._key)}
                          disabled={aiSaving}
                        >
                          {isEditing ? "Done" : "Edit"}
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          variant="outlined"
                          onClick={() => { if (isEditing) setAiEditingKey(null); handleAiDiscardQuestion(q._key); }}
                          disabled={aiSaving}
                        >
                          Discard
                        </Button>
                      </Box>
                    </Box>
                  </Paper>
                );
              })}

              {aiSaving && <LinearProgress />}
            </Stack>
          )}
        </DialogContent>

        <DialogActions sx={{ px: 3, py: 2 }}>
          {aiStep === 1 && (
            <>
              <Button onClick={() => { setAiDialogOpen(false); resetAiDialog(); }} disabled={aiGenerating}>
                Cancel
              </Button>
              <Button
                variant="contained"
                onClick={handleAiGenerate}
                disabled={
                  aiGenerating
                  || !aiFile
                  || aiSelectedTypes.size === 0
                  || Object.values(aiDifficultyDistribution).reduce((a, b) => a + b, 0) === 0
                  || !hasCompatibleGenerationPlan
                }
              >
                {aiGenerating ? "Generating…" : "Generate Questions"}
              </Button>
            </>
          )}
          {aiStep === 2 && (
            <>
              <Button onClick={() => { setAiStep(1); setAiSaveError(""); }} disabled={aiSaving}>
                Back
              </Button>
              <Button
                variant="contained"
                onClick={handleAiSaveAll}
                disabled={aiSaving || aiGeneratedQuestions.length === 0}
              >
                {aiSaving ? "Saving…" : `Save ${aiGeneratedQuestions.length} Question${aiGeneratedQuestions.length !== 1 ? "s" : ""}`}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Questions;
