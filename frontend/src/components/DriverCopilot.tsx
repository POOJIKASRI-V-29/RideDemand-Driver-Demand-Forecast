import type { CopilotResponse } from "../types/demand";

interface Props {
  copilot: CopilotResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  disabled: boolean;
}

/**
 * The driver-facing briefing.
 *
 * The text is written from the backend's own prediction figures. When no LLM
 * key is configured the backend answers with a deterministic template instead,
 * and the footer says which of the two produced this text.
 */
export function DriverCopilot({ copilot, loading, error, onRefresh, disabled }: Props) {
  const provenance = copilot
    ? copilot.source === "llm"
      ? `AI-generated · ${copilot.model ?? "llm"}`
      : "Deterministic fallback · no LLM key"
    : "Awaiting forecast";

  return (
    <div className="copilot">
      <div className="copilot__head">
        <span aria-hidden="true">🤖</span>
        Driver Copilot
        <button
          type="button"
          className="copilot__refresh"
          onClick={onRefresh}
          disabled={loading || disabled}
          aria-label="Regenerate the driver briefing"
          title="Regenerate the driver briefing"
        >
          ↻
        </button>
      </div>

      <div className="copilot__text" aria-live="polite">
        {loading ? (
          <>
            <span className="copilot__skeleton" style={{ width: "100%" }} />
            <span className="copilot__skeleton" style={{ width: "92%" }} />
            <span className="copilot__skeleton" style={{ width: "68%" }} />
          </>
        ) : error ? (
          <span style={{ color: "oklch(0.78 0.12 27)" }}>{error}</span>
        ) : copilot ? (
          <p style={{ margin: 0 }}>{copilot.message}</p>
        ) : (
          <p style={{ margin: 0, color: "rgba(255,255,255,.55)" }}>
            Generate a forecast and the copilot will explain where the demand is.
          </p>
        )}
      </div>

      <div className="copilot__foot">
        <span>{provenance}</span>
        <span className="copilot__endpoint">POST /api/copilot</span>
      </div>
    </div>
  );
}
