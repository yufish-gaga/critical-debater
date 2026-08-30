import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "../api";
import type { RootState } from "../store";
import type { EvidenceItem } from "../types";

const TIERS = ["all", "tier1_authoritative", "tier2_reputable", "tier3_general", "tier4_social"];

/** 证据浏览器 / Evidence browser with credibility + language labels. */
export function EvidenceBrowser({ refreshToken }: { refreshToken: number }) {
  const debateId = useSelector((s: RootState) => s.debate.debateId);
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [tierFilter, setTierFilter] = useState("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!debateId) return;
    api
      .artifact<EvidenceItem[]>(debateId, "evidence_store")
      .then((a) => setItems(a.exists ? (a.data ?? []) : []))
      .catch(() => setItems([]));
  }, [debateId, refreshToken]);

  const filtered = items.filter((e) => {
    if (tierFilter !== "all" && e.credibility_tier !== tierFilter) return false;
    if (!query) return true;
    const haystack = `${e.publisher} ${e.snippet} ${e.url}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        证据浏览器({items.length})
      </Typography>
      <TextField
        select
        size="small"
        label="可信度分级"
        value={tierFilter}
        onChange={(e) => setTierFilter(e.target.value)}
        sx={{ width: 240, mb: 2, mr: 2 }}
      >
        {TIERS.map((t) => (
          <MenuItem key={t} value={t}>
            {t}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        size="small"
        label="搜索"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        sx={{ width: 280, mb: 2 }}
      />
      <TableContainer sx={{ maxHeight: 480 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>编号</TableCell>
              <TableCell>分级</TableCell>
              <TableCell>评分</TableCell>
              <TableCell>语言</TableCell>
              <TableCell>来源</TableCell>
              <TableCell>交叉验证</TableCell>
              <TableCell>摘要</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.map((e) => (
              <TableRow key={e.evidence_id}>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.evidence_id}</TableCell>
                <TableCell>{e.credibility_tier?.replace("tier", "T").replace("_authoritative", " ★").replace("_reputable", "").replace("_general", "").replace("_social", " ⚠")}</TableCell>
                <TableCell>{e.credibility_score != null ? e.credibility_score.toFixed(2) : "—"}</TableCell>
                <TableCell>{e.source_language ?? "—"}</TableCell>
                <TableCell>{e.publisher || "—"}</TableCell>
                <TableCell>{e.corroboration_status ?? "—"}</TableCell>
                <TableCell sx={{ maxWidth: 380, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {e.snippet}
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>暂无证据</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}
