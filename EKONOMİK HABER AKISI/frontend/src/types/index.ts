export interface NewsItem {
  id: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  category: string;
  published_at: string;
  logo: string;
}

export interface TimeEffect {
  period: string;
  effect: string;
  direction: "positive" | "negative" | "neutral";
}

export interface AffectedCompany {
  ticker: string;
  name: string;
  impact: "positive" | "negative" | "neutral";
  reason: string;
}

export interface AffectedSector {
  name: string;
  impact: "positive" | "negative" | "neutral";
  reason: string;
}

export interface ActionSuggestion {
  headline: string;
  watch_list: {
    ticker: string;
    name: string;
    action: "Al" | "Sat" | "İzle" | "Dikkat";
    reason: string;
  }[];
  risk_warning: string;
  opportunity: string;
}

export interface AnalysisResult {
  simple_explanation: string;
  action_suggestion?: ActionSuggestion;
  time_effects: {
    short_term: TimeEffect;
    medium_term: TimeEffect;
    long_term: TimeEffect;
  };
  affected_companies: AffectedCompany[];
  affected_sectors: AffectedSector[];
  sentiment_score: number;
  sentiment_label: string;
  key_takeaway: string;
}

export interface Analyst {
  id: number;
  name: string;
  expertise: string;
  description: string;
  twitter: string;
  youtube: string;
  avatar_color: string;
}
