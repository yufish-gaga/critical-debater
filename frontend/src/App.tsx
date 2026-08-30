import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { EvidenceBrowser } from "./components/EvidenceBrowser";
import { LiveProgress } from "./components/LiveProgress";
import { QualityPanel } from "./components/QualityPanel";
import { ReportView } from "./components/ReportView";
import { RoundsView } from "./components/RoundsView";
import { TopicConfig } from "./components/TopicConfig";
import { useDebateSocket } from "./hooks/useDebateSocket";
import { attachDebate } from "./slices/debateSlice";
import { clearSavedDebateId, loadSavedDebateId } from "./session";
import type { AppDispatch, RootState } from "./store";

const TABS = [
  "配置",
  "进度",
  "证据",
  "轮次",
  "质量",
  "报告",
];

export default function App() {
  const [tab, setTab] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const dispatch = useDispatch<AppDispatch>();
  const debateId = useSelector((s: RootState) => s.debate.debateId);
  const status = useSelector((s: RootState) => s.debate.status?.status);

  // Re-attach to the debate from a previous page session, if it still exists
  // server-side; a stale id (server restarted) is simply dropped.
  useEffect(() => {
    const saved = loadSavedDebateId();
    if (saved) {
      dispatch(attachDebate(saved))
        .unwrap()
        .catch(() => clearSavedDebateId());
    }
  }, [dispatch]);

  // WS live feed while a debate is active; artifacts refresh on demand.
  useDebateSocket(debateId);
  const running = Boolean(status && !["complete"].includes(status) && !status.startsWith("failed_"));

  const bump = () => setRefreshToken((t) => t + 1);

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "grey.100" }}>
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar>
          <Typography variant="h6" sx={{ mr: 2 }}>
            ⚖ Critical Debater
          </Typography>
          {debateId && (
            <Stack direction="row" spacing={1}>
              <Chip size="small" label={`debate ${debateId}`} variant="outlined" />
              {status && <Chip size="small" color={running ? "info" : "success"} label={status} />}
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ px: 2, bgcolor: "background.paper" }}>
        {TABS.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>

      <Box sx={{ p: 3, maxWidth: 1100, mx: "auto" }}>
        {tab === 0 && (
          <TopicConfig
            onStarted={() => {
              setTab(1);
              bump();
            }}
          />
        )}        {tab === 1 && <LiveProgress />}
        {tab === 2 && <EvidenceBrowser refreshToken={refreshToken} />}
        {tab === 3 && <RoundsView refreshToken={refreshToken} />}
        {tab === 4 && <QualityPanel refreshToken={refreshToken} />}
        {tab === 5 && <ReportView refreshToken={refreshToken} />}
      </Box>
    </Box>
  );
}
