import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "../api";
import type { RootState } from "../store";

/** 最终报告展示 / Final report (bilingual markdown). */
export function ReportView({ refreshToken }: { refreshToken: number }) {
  const debateId = useSelector((s: RootState) => s.debate.debateId);
  const [markdown, setMarkdown] = useState<string | null>(null);

  useEffect(() => {
    if (!debateId) return;
    api
      .reportMarkdown(debateId)
      .then(setMarkdown)
      .catch(() => setMarkdown(null));
  }, [debateId, refreshToken]);

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        最终报告 / Final report
      </Typography>
      {markdown ? (
        <Typography
          component="pre"
          sx={{
            whiteSpace: "pre-wrap",
            fontFamily: '"PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
            fontSize: 14,
            lineHeight: 1.7,
            maxHeight: 640,
            overflow: "auto",
          }}
        >
          {markdown}
        </Typography>
      ) : (
        <Typography color="text.secondary">
          报告尚未生成 / report not generated yet
        </Typography>
      )}
    </Paper>
  );
}
