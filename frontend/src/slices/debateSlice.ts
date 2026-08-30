import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { api } from "../api";
import type { AuditEntry, DebateStartRequest, DebateStatus } from "../types";

interface DebateState {
  debateId: string | null;
  status: DebateStatus | null;
  audit: AuditEntry[];
  wsConnected: boolean;
  error: string | null;
  starting: boolean;
}

const initialState: DebateState = {
  debateId: null,
  status: null,
  audit: [],
  wsConnected: false,
  error: null,
  starting: false,
};

export const startDebate = createAsyncThunk(
  "debate/start",
  async (req: DebateStartRequest, { dispatch }) => {
    const status = await api.startDebate(req);
    dispatch(debateSlice.actions.setStatus(status));
    return status;
  },
);

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
      });
  },
});

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
