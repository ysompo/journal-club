import { useState, FormEvent, useEffect, useCallback } from "react";
import { api } from "@jc/shared";
import { useSidecar, SidecarEvent } from "../hooks/useSidecar";
import { getStoredUserId } from "../store/auth";

interface Props {
  onClose: () => void;
  onArticleAdded: () => void;
  hujiEmail: string;
  hujiPassword: string;
  chromePath: string;
  chromeProfile: string;
}

type Step = "input" | "downloading" | "done" | "error";

export function AddArticleModal({
  onClose,
  onArticleAdded,
  hujiEmail,
  hujiPassword,
  chromePath,
  chromeProfile,
}: Props) {
  const [input, setInput] = useState("");
  const [step, setStep] = useState<Step>("input");
  const [messages, setMessages] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState("");

  const addMessage = useCallback((msg: string) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const handleEvent = useCallback(
    (event: SidecarEvent) => {
      switch (event.type) {
        case "progress":
          addMessage(event.message);
          break;
        case "metadata":
          addMessage(`Found: ${(event.article as { title?: string }).title ?? "article"}`);
          break;
        case "done":
          setStep("done");
          onArticleAdded();
          break;
        case "error":
          setStep("error");
          setErrorMsg(event.message);
          break;
      }
    },
    [addMessage, onArticleAdded]
  );

  const { startDownload, cleanup } = useSidecar({ onEvent: handleEvent });

  useEffect(() => () => cleanup(), [cleanup]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;

    setStep("downloading");
    setMessages([]);

    try {
      // 1. Enqueue on the backend so other devices can see it
      const queueItem = await api.enqueue(input.trim());

      // 2. Kick off the sidecar download on this desktop
      const userId = getStoredUserId() ?? "unknown";
      const deviceId = userId; // use userId as deviceId for now (Phase 1 simplification)
      const token = localStorage.getItem("jc_access_token") ?? "";
      const apiUrl = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8765";

      await startDownload({
        input: input.trim(),
        queue_item_id: queueItem.id,
        device_id: deviceId,
        api_url: apiUrl,
        token,
        huji_email: hujiEmail,
        huji_password: hujiPassword,
        chrome_profile: chromeProfile,
        chrome_path: chromePath,
      });
    } catch (err) {
      setStep("error");
      setErrorMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
      onClick={(e) => { if (e.target === e.currentTarget && step !== "downloading") onClose(); }}
    >
      <div
        style={{
          background: "var(--color-surface-container-lowest)",
          border: "1px solid var(--color-outline-variant)",
          borderRadius: "var(--radius-lg)",
          padding: "1.5rem",
          width: "100%",
          maxWidth: 520,
          boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-headline)",
            fontSize: "1.25rem",
            color: "var(--color-on-surface)",
            margin: "0 0 1rem",
          }}
        >
          Add article
        </h2>

        {step === "input" && (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "0.8125rem",
                  fontFamily: "var(--font-label)",
                  color: "var(--color-on-surface-variant)",
                  marginBottom: "0.375rem",
                }}
              >
                URL, PubMed ID, or DOI
              </label>
              <input
                autoFocus
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="https://pubmed.ncbi.nlm.nih.gov/39794646  or  10.1056/NEJM…"
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  border: "1px solid var(--color-outline-variant)",
                  borderRadius: "var(--radius)",
                  background: "var(--color-surface-container)",
                  color: "var(--color-on-surface)",
                  fontFamily: "var(--font-body)",
                  fontSize: "0.9rem",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </div>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: "0.5rem 0.875rem",
                  background: "none",
                  border: "1px solid var(--color-outline-variant)",
                  borderRadius: "var(--radius)",
                  cursor: "pointer",
                  fontFamily: "var(--font-label)",
                  color: "var(--color-on-surface-variant)",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!input.trim()}
                style={{
                  padding: "0.5rem 1rem",
                  background: "var(--color-primary)",
                  color: "var(--color-on-primary)",
                  border: "none",
                  borderRadius: "var(--radius)",
                  fontFamily: "var(--font-label)",
                  fontWeight: 500,
                  cursor: input.trim() ? "pointer" : "not-allowed",
                  opacity: input.trim() ? 1 : 0.5,
                }}
              >
                Download
              </button>
            </div>
          </form>
        )}

        {step === "downloading" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p style={{ margin: 0, color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>
              Downloading — please keep this window open…
            </p>
            <div
              style={{
                background: "var(--color-surface-container)",
                borderRadius: "var(--radius)",
                padding: "0.75rem",
                maxHeight: 200,
                overflowY: "auto",
                fontFamily: "monospace",
                fontSize: "0.75rem",
                color: "var(--color-on-surface-variant)",
                display: "flex",
                flexDirection: "column",
                gap: "0.25rem",
              }}
            >
              {messages.map((m, i) => <span key={i}>{m}</span>)}
              {messages.length === 0 && <span>Starting…</span>}
            </div>
          </div>
        )}

        {step === "done" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <p style={{ margin: 0, color: "var(--color-primary)", fontWeight: 500 }}>
              ✓ Article downloaded and saved successfully.
            </p>
            <button
              onClick={onClose}
              style={{
                alignSelf: "flex-end",
                padding: "0.5rem 1rem",
                background: "var(--color-primary)",
                color: "var(--color-on-primary)",
                border: "none",
                borderRadius: "var(--radius)",
                fontFamily: "var(--font-label)",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Done
            </button>
          </div>
        )}

        {step === "error" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <p style={{ margin: 0, color: "var(--color-error)", fontSize: "0.875rem" }}>
              Download failed: {errorMsg}
            </p>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button
                onClick={() => { setStep("input"); setMessages([]); setErrorMsg(""); }}
                style={{
                  padding: "0.5rem 0.875rem",
                  background: "none",
                  border: "1px solid var(--color-outline-variant)",
                  borderRadius: "var(--radius)",
                  cursor: "pointer",
                  fontFamily: "var(--font-label)",
                  color: "var(--color-on-surface-variant)",
                }}
              >
                Try again
              </button>
              <button
                onClick={onClose}
                style={{
                  padding: "0.5rem 0.875rem",
                  background: "none",
                  border: "1px solid var(--color-outline-variant)",
                  borderRadius: "var(--radius)",
                  cursor: "pointer",
                  fontFamily: "var(--font-label)",
                  color: "var(--color-on-surface-variant)",
                }}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
