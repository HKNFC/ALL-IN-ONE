import axios from "axios";
import type { AnalysisResult, Analyst, NewsItem } from "../types";

const api = axios.create({ baseURL: "http://localhost:8000" });

export async function fetchNews(limit = 50): Promise<NewsItem[]> {
  const { data } = await api.get(`/api/news?limit=${limit}`);
  return data.data;
}

export async function analyzeNews(title: string, content: string): Promise<AnalysisResult> {
  const { data } = await api.post("/api/analyze", { title, content });
  return data.data;
}

export async function analyzeManual(text: string): Promise<AnalysisResult> {
  const { data } = await api.post("/api/analyze/manual", { text });
  return data.data;
}

export async function fetchAnalysts(): Promise<Analyst[]> {
  const { data } = await api.get("/api/analysts");
  return data.data;
}

export async function checkHealth(): Promise<{ status: string; api_key_configured: boolean }> {
  const { data } = await api.get("/api/health");
  return data;
}
