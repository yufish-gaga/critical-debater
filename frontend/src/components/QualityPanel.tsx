import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";
import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "../api";
import type { RootState } from "../store";
import type { QualityReport } from "../types";

/** 质量评估仪表盘 / Quality dashboard: 8-dimension radar + table. */
export function QualityPanel({ refreshToken }: { refreshToken: number }) {
  const debateId = useSelector((s: RootState) => s.debate.debateId);
  const [report, setReport] = useState<QualityReport | null>(null);

  useEffect(() => {
    if (!debateId) return;
    api
      .quality(debateId)
      .then(setReport)
      .catch(() => setReport(null));
  }, [debateId, refreshToken]);

  if (!report) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">
          质量报告在辩论完成后生成
        </Typography>
      </Paper>
    );
  }

  const data = report.dimensions.map((d) => ({
    dim: d.label.split(" / ")[0],
    score: d.score,
  }));

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        质量评估 — 综合 {report.overall_score.toFixed(2)}
      </Typography>
      <div style={{ width: "100%", height: 360 }}>
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid />
            <PolarAngleAxis dataKey="dim" tick={{ fontSize: 12 }} />
            <PolarRadiusAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
            <Radar dataKey="score" stroke="#2563eb" fill="#2563eb" fillOpacity={0.25} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <TableContainer>
        <Table size="small">
          <TableBody>
            {report.dimensions.map((d) => (
              <TableRow key={d.dimension}>
                <TableCell>{d.label.split(" / ")[0]}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {d.score.toFixed(2)}
                </TableCell>
                <TableCell sx={{ color: "text.secondary", fontSize: 12 }}>{d.notes.join("；")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}
