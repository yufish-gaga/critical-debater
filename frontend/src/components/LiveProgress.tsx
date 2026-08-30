import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepContent from "@mui/material/StepContent";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";
import { useSelector } from "react-redux";
import type { RootState } from "../store";

const STAGES = [
  { key: "initialized", label: "初始化 / initialized" },
  { key: "evidence_gathered", label: "证据采集 / evidence gathered" },
  { key: "in_progress", label: "辩论轮次 / rounds in progress" },
  { key: "final_synthesis", label: "综合报告 / final synthesis" },
  { key: "complete", label: "质量评估 / quality assessment" },
];

function stageIndex(status: string): number {
  if (status.startsWith("round_") && status.endsWith("_complete")) return 2;
  const idx = STAGES.findIndex((s) => s.key === status);
  return idx === -1 ? (status.startsWith("failed_") ? 2 : 0) : idx;
}

/** 实时进度监控 / Live progress monitor fed by the WebSocket audit stream. */
export function LiveProgress() {
  const debate = useSelector((s: RootState) => s.debate);
  const status = debate.status?.status ?? "pending";
  const failed = status.startsWith("failed_");
  const done = status === "complete";
  const activeIdx = failed ? 2 : done ? STAGES.length - 1 : stageIndex(status);

  return (
    <Paper sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h6">实时进度 / Live progress</Typography>
        <Chip
          size="small"
          color={debate.wsConnected ? "success" : "default"}
          label={debate.wsConnected ? "WebSocket 已连接 / live" : "未连接 / offline"}
        />
        <Chip size="small" color={failed ? "error" : done ? "success" : "info"} label={status} />
      </Stack>

      {debate.status?.error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {debate.status.error}
        </Alert>
      )}

      <Stepper activeStep={activeIdx} orientation="vertical" nonLinear>
        {STAGES.map((stage, idx) => (
          <Step key={stage.key} completed={idx < activeIdx || done}>
            <StepLabel error={failed && idx === activeIdx}>{stage.label}</StepLabel>
            <StepContent>
              {stage.key === "in_progress" && (
                <Typography variant="body2" color="text.secondary">
                  当前轮 / current round: {debate.status?.current_round ?? "-"} / {debate.status?.rounds ?? "-"}
                </Typography>
              )}
            </StepContent>
          </Step>
        ))}
      </Stepper>

      <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
        审计事件流 / audit trail
      </Typography>
      <List dense sx={{ maxHeight: 320, overflow: "auto", bgcolor: "grey.50", borderRadius: 1 }}>
        {[...debate.audit].reverse().map((entry, idx) => (
          <ListItem key={`${entry.timestamp}-${idx}`} divider>
            <ListItemText
              primary={entry.action}
              secondary={JSON.stringify(entry.details).slice(0, 140)}
              primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
              secondaryTypographyProps={{ variant: "caption" }}
            />
          </ListItem>
        ))}
        {debate.audit.length === 0 && (
          <ListItem>
            <ListItemText secondary="等待事件… / waiting for events…" />
          </ListItem>
        )}
      </List>
    </Paper>
  );
}
