import { useEffect, useRef } from "react";
import { useDispatch } from "react-redux";
import { applySnapshot, applyStatusEvent, pushAudit, setWsConnected } from "../slices/debateSlice";
import type { AuditEntry } from "../types";

const TERMINAL = new Set(["complete", "cancelled", "failed_initialization", "failed_final_synthesis", "failed_report_validation"]);
const isTerminal = (s: string) => TERMINAL.has(s) || s.startsWith("failed_");

/**
 * Live progress over native WebSocket: snapshot → audit/status events.
 * Reconnects with backoff while the run is active; closes for good once a
 * terminal status arrives. Opens only when a debate is attached.
 */
export function useDebateSocket(debateId: string | null): void {
  const dispatch = useDispatch();
  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const terminalRef = useRef(false);

  useEffect(() => {
    if (!debateId) return;
    terminalRef.current = false;
    let closedByUs = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const token = localStorage.getItem("cd_api_token") ?? "";
      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/${debateId}${query}`);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        dispatch(setWsConnected(true));
      };
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data as string) as
          | { type: "snapshot"; debate_id: string; topic: string; rounds: number; status: string; audit: AuditEntry[]; error?: string | null }
          | { type: "audit"; entry: AuditEntry }
          | { type: "status"; status: string };
        if (msg.type === "snapshot") {
          terminalRef.current = isTerminal(msg.status);
          dispatch(applySnapshot(msg));
        } else if (msg.type === "audit") {
          dispatch(pushAudit(msg.entry));
          return; // audit events never close the socket
        } else if (msg.type === "status") {
          terminalRef.current = isTerminal(msg.status);
          dispatch(applyStatusEvent(msg.status));
        }
        if (terminalRef.current) ws.close();
      };
      ws.onclose = () => {
        dispatch(setWsConnected(false));
        if (!closedByUs && !terminalRef.current && attemptRef.current < 5) {
          attemptRef.current += 1;
          timer = setTimeout(connect, 500 * attemptRef.current);
        }
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closedByUs = true;
      if (timer) clearTimeout(timer);
      socketRef.current?.close();
      dispatch(setWsConnected(false));
    };
  }, [debateId, dispatch]);
}
