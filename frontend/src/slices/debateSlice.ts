import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { api } from "../api";
import { saveDebateId } from "../session";
import type { AuditEntry, DebateStartRequest, DebateStatus } from "../types";

interface DebateState {
  debateId: string | null;
  status: DebateStatus | null;
  audit: AuditEntry[];
  wsConnected: boolean;
  error: string | null;
  starting: boolean;
  attaching: boolean;
}

const initialState: DebateState = {
  debateId: null,
  status: null,
  audit: [],
  wsConnected: false,
  error: null,
  starting: false,
  attaching: false,
};

const debateSlice = createSlice({
  name: "debate",
  initialState,
  reducers: {
    setDebateId(state, action: PayloadAction<string>) {
      state.debateId = action.payload;
      state.audit = [];
      state.error = null;
    },
    setStatus(state, action: PayloadAction<DebateStatus>) {
      state.status = action.payload;
    },
    applySnapshot(
      state,
      action: PayloadAction<{ debate_id: string; status: string; topic: string; rounds: number; audit: AuditEntry[]; error?: string | null }>,
    ) {
      state.debateId = action.payload.debate_id;
      state.audit = action.payload.audit;
      if (state.status) {
        state.status.status = action.payload.status;
        state.status.error = action.payload.error ?? null;
      } else {
        // First contact after a cold restore: build the minimum the UI needs.
        state.status = {
          debate_id: action.payload.debate_id,
          workspace: "",
          topic: action.payload.topic,
          rounds: action.payload.rounds,
          current_round: 0,
          status: action.payload.status,
          started_at: null,
          finished_at: null,
          error: action.payload.error ?? null,
        };
      }
    },
    pushAudit(state, action: PayloadAction<AuditEntry>) {
      state.audit.push(action.payload);
      if (state.audit.length > 300) state.audit.shift();
    },
    applyStatusEvent(state, action: PayloadAction<string>) {
      if (state.status) state.status.status = action.payload;
    },
    setWsConnected(state, action: PayloadAction<boolean>) {
      state.wsConnected = action.payload;
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(startDebate.pending, (state) => {
        state.starting = true;
        state.error = null;
      })
      .addCase(startDebate.fulfilled, (state) => {
        state.starting = false;
      })
      .addCase(startDebate.rejected, (state, action) => {
        state.starting = false;
        state.error = action.error.message ?? "start failed";
      })
      .addCase(attachDebate.pending, (state) => {
        state.attaching = true;
      })
      .addCase(attachDebate.fulfilled, (state) => {
        state.attaching = false;
      })
      .addCase(attachDebate.rejected, (state) => {
        // Auto-restore on load: the run may be gone (server restarted).
        // App clears the stale id; no user-facing error.
        state.attaching = false;
      });
  },
});

/** Start a debate and adopt it as the active one (id kept for reload). */
export const startDebate = createAsyncThunk(
  "debate/start",
  async (req: DebateStartRequest, { dispatch }) => {
    const status = await api.startDebate(req);
    saveDebateId(status.debate_id);
    dispatch(debateSlice.actions.setDebateId(status.debate_id));
    dispatch(debateSlice.actions.setStatus(status));
    return status;
  },
);

/** Re-attach to a debate that is running (or finished) on the server. */
export const attachDebate = createAsyncThunk(
  "debate/attach",
  async (id: string, { dispatch }) => {
    const status = await api.getStatus(id);
    saveDebateId(id);
    dispatch(debateSlice.actions.setDebateId(id));
    dispatch(debateSlice.actions.setStatus(status));
    return status;
  },
);

export const {
  setDebateId,
  setStatus,
  applySnapshot,
  pushAudit,
  applyStatusEvent,
  setWsConnected,
  setError,
} = debateSlice.actions;

export default debateSlice.reducer;
