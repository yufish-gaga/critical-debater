// Shared API types mirroring the FastAPI schemas and data contracts.

export interface DebateStatus {
  debate_id: string;
  workspace: string;
  topic: string;
  rounds: number;
  current_round: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface DebateStartRequest {
  topic: string;
  rounds: number;
  depth: string;
  mode: string;
  language: string;
  workspace?: string;
}

export interface AuditEntry {
  timestamp: string;
  action: string;
  details: Record<string, unknown>;
}

export interface EvidenceItem {
  evidence_id: string;
  source_type: string;
  url: string;
  publisher: string;
  published_at: string | null;
  snippet: string;
  credibility_tier: string;
  freshness_status: string;
  evidence_track: string;
  corroboration_status?: string | null;
  credibility_score?: number;
  source_language?: string;
  discovered_by?: string;
  discovered_at_round?: number;
}

export interface Argument {
  claim_text: string;
  claim_type: string;
  evidence_ids: string[];
  reasoning_chain: Record<string, string>;
}

export interface TurnArtifact {
  round: number;
  side: string;
  arguments: Argument[];
  rebuttals: { target_claim_id: string; rebuttal_text: string }[];
  mandatory_responses?: { point_id: string; response_text: string }[];
}

export interface JudgeRuling {
  round: number;
  verification_results: { claim_id: string; new_status: string; reasoning: string }[];
  causal_validity_flags: { claim_id: string; issue: string; severity: string }[];
  mandatory_response_points: { point_id: string; target: string; point: string }[];
  round_summary: string;
}

export interface QualityDimension {
  dimension: string;
  label: string;
  score: number;
  notes: string[];
}

export interface QualityReport {
  topic: string;
  mode: string;
  overall_score: number;
  rounds_completed: number;
  rounds_planned: number;
  generated_at: string;
  dimensions: QualityDimension[];
  baseline: {
    evidence: { total: number; by_credibility_tier: Record<string, number>; by_source_language: Record<string, number> };
    claims: { total: number; by_status: Record<string, number> };
    credibility: { average: number };
  };
}
