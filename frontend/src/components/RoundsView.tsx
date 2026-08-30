import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "../api";
import type { RootState } from "../store";
import type { JudgeRuling, TurnArtifact } from "../types";

interface RoundData {
  round: number;
  pro: TurnArtifact | null;
  con: TurnArtifact | null;
  judge: JudgeRuling | null;
}

/** 辩论轮次视图 / Round-by-round view: arguments, rebuttals, judge ruling. */
export function RoundsView({ refreshToken }: { refreshToken: number }) {
  const debate = useSelector((s: RootState) => s.debate);
  const debateId = debate.debateId;
  const totalRounds = debate.status?.rounds ?? 0;
  const [rounds, setRounds] = useState<RoundData[]>([]);

  const load = useCallback(async () => {
    if (!debateId) return;
    const data: RoundData[] = [];
    for (let round = 1; round <= Math.max(totalRounds, debate.status?.current_round ?? 0); round++) {
      const [pro, con, judge] = await Promise.all([
        api.turn(debateId, round, "pro"),
        api.turn(debateId, round, "con"),
        api.judgeRuling(debateId, round),
      ]);
      if (pro || con || judge) data.push({ round, pro, con, judge });
    }
    setRounds(data);
  }, [debateId, totalRounds, debate.status?.current_round]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  if (!debateId) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">先启动一场辩论</Typography>
      </Paper>
    );
  }

  return (
    <Stack spacing={2}>
      {rounds.map(({ round, pro, con, judge }) => (
        <Accordion key={round} defaultExpanded={round === 1}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={2} alignItems="center">
              <Typography variant="subtitle1" fontWeight={700}>
                第 {round} 轮
              </Typography>
              <Chip size="small" label={`正方 ${pro?.arguments.length ?? 0} 论点`} />
              <Chip size="small" label={`反方 ${con?.arguments.length ?? 0} 论点`} />
              <Chip
                size="small"
                color="warning"
                label={`${judge?.causal_validity_flags.length ?? 0} 因果标记`}
              />
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            {(["pro", "con"] as const).map((side) => {
              const turn = side === "pro" ? pro : con;
              if (!turn) return null;
              return (
                <Paper key={side} variant="outlined" sx={{ p: 2, mb: 2 }}>
                  <Typography variant="subtitle2" color={side === "pro" ? "primary" : "secondary"}>
                    {side === "pro" ? "正方" : "反方"}
                  </Typography>
                  {turn.arguments.map((arg, i) => (
                    <Stack key={i} spacing={0.5} sx={{ mt: 1 }}>
                      <Typography variant="body1">
                        {i + 1}. {arg.claim_text}{" "}
                        <Chip size="small" variant="outlined" label={arg.claim_type} />
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        机制: {arg.reasoning_chain?.mechanism ?? "—"}
                      </Typography>
                    </Stack>
                  ))}
                  {turn.rebuttals.length > 0 && (
                    <>
                      <Divider sx={{ my: 1 }} />
                      {turn.rebuttals.map((r, i) => (
                        <Typography key={i} variant="body2">
                          ↩ 驳 {r.target_claim_id}: {r.rebuttal_text}
                        </Typography>
                      ))}
                    </>
                  )}
                </Paper>
              );
            })}
            {judge && (
              <Paper variant="outlined" sx={{ p: 2, bgcolor: "grey.50" }}>
                <Typography variant="subtitle2">裁判 — {judge.round_summary}</Typography>
                {judge.verification_results.map((v, i) => (
                  <Typography key={i} variant="caption" display="block">
                    {v.claim_id} → {v.new_status}: {v.reasoning}
                  </Typography>
                ))}
              </Paper>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
      {rounds.length === 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography color="text.secondary">暂无轮次数据</Typography>
        </Paper>
      )}
    </Stack>
  );
}
