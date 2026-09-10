interface Props {
  message?: string;
  /** Renders as a compact bar rather than a full card. */
  inline?: boolean;
}

export function LoadingState({ message = "Generating forecast…", inline = true }: Props) {
  return (
    <div className={inline ? "state state--inline" : "state"} role="status" aria-live="polite">
      <span className="spinner spinner--dark" aria-hidden="true" />
      <div className="state__title">{message}</div>
    </div>
  );
}
