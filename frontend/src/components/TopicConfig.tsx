import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { startDebate } from "../slices/debateSlice";
import type { AppDispatch, RootState } from "../store";
import type { DebateStartRequest } from "../types";

/** 辩题配置面板 / Topic configuration panel. */
export function TopicConfig({ onStarted }: { onStarted: (id: string) => void }) {
  const dispatch = useDispatch<AppDispatch>();
  const starting = useSelector((s: RootState) => s.debate.starting);
  const [form, setForm] = useState<DebateStartRequest>({
    topic: "",
    rounds: 3,
    depth: "standard",
    mode: "balanced",
    language: "bilingual",
  });

  const set = <K extends keyof DebateStartRequest>(key: K, value: DebateStartRequest[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    const result = await dispatch(startDebate(form));
    if (startDebate.fulfilled.match(result)) {
      onStarted(result.payload.debate_id);
    }
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        辩题配置 / Topic configuration
      </Typography>
      <Stack spacing={2}>
        <TextField
          label="辩题 / Topic"
          multiline
          minRows={2}
          value={form.topic}
          onChange={(e) => set("topic", e.target.value)}
          placeholder="例：中国应全面放开低空经济管制 / Example: Should low-altitude economy be fully liberalized?"
        />
        <Stack direction="row" spacing={2}>
          <TextField
            label="轮数 / Rounds"
            type="number"
            value={form.rounds}
            onChange={(e) => set("rounds", Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
            sx={{ width: 120 }}
          />
          <TextField
            select
            label="深度 / Depth"
            value={form.depth}
            onChange={(e) => set("depth", e.target.value)}
            sx={{ width: 160 }}
          >
            <MenuItem value="quick">quick 快速</MenuItem>
            <MenuItem value="standard">standard 标准</MenuItem>
            <MenuItem value="deep">deep 深度</MenuItem>
          </TextField>
          <TextField
            select
            label="模式 / Mode"
            value={form.mode}
            onChange={(e) => set("mode", e.target.value)}
            sx={{ width: 180 }}
          >
            <MenuItem value="balanced">balanced 平衡</MenuItem>
            <MenuItem value="red_team">red_team 红队</MenuItem>
          </TextField>
          <TextField
            select
            label="语言 / Language"
            value={form.language}
            onChange={(e) => set("language", e.target.value)}
            sx={{ width: 180 }}
          >
            <MenuItem value="bilingual">bilingual 双语</MenuItem>
            <MenuItem value="zh">中文</MenuItem>
            <MenuItem value="en">English</MenuItem>
          </TextField>
        </Stack>
        <Button variant="contained" disabled={starting || !form.topic.trim()} onClick={submit}>
          {starting ? "启动中… / starting…" : "开始辩论 / Start debate"}
        </Button>
      </Stack>
    </Paper>
  );
}
