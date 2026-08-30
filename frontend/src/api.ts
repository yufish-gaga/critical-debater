import type {
  DebateStartRequest,
  DebateStatus,
  JudgeRuling,
  QualityReport,
  TurnArtifact,
} from "./types";

const BASE = "";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export interface Artifact<T = unknown> {
  debate_id: string;
  name: string;
  exists: boolean;
  data: T;
}

export const api = {
  async startDebate(req: DebateStartRequest): Promise<DebateStatus> {
    const res = await fetch(`${BASE}/api/debates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`start failed: ${res.status}`);
    const start = (await res.json()) as { debate_id: string };
    return this.getStatus(start.debate_id);
  },

  getStatus: (id: string): Promise<DebateStatus> => getJson(`/api/debates/${id}`),

  artifact: <T>(id: string, name: string): Promise<Artifact<T>> =>
    getJson(`/api/debates/${id}/artifacts/${name}`),

  turn: (id: string, round: number, side: "pro" | "con"): Promise<TurnArtifact | null> =>
    getJson<Artifact<TurnArtifact>>(`/api/debates/${id}/artifacts/round_${round}_${side}_turn`)
      .then((a) => (a.exists ? a.data : null)),

  judgeRuling: (id: string, round: number): Promise<JudgeRuling | null> =>
    getJson<Artifact<JudgeRuling>>(`/api/debates/${id}/artifacts/round_${round}_judge_ruling`)
      .then((a) => (a.exists ? a.data : null)),

  quality: (id: string): Promise<QualityReport | null> =>
    getJson<Artifact<QualityReport>>(`/api/debates/${id}/artifacts/quality_metrics`)
      .then((a) => (a.exists ? a.data : null)),

  reportMarkdown: async (id: string): Promise<string | null> => {
    const res = await fetch(`${BASE}/api/debates/${id}/report`);
    if (!res.ok) return null;
    const body = (await res.json()) as { exists: boolean; content: string | null };
    return body.content;
  },
};

/** Artifact endpoint URL for arbitrary named artifacts. */
export function artifactUrl(debateId: string, name: string): string {
  return `${BASE}/api/debates/${debateId}/artifacts/${name}`;
}
