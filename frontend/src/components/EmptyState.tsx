interface Props {
  onPredict: () => void;
  title?: string;
  body?: string;
}

export function EmptyState({
  onPredict,
  title = "No forecast yet",
  body = "Choose a day, a time and a forecast window, then generate a demand forecast.",
}: Props) {
  return (
    <div className="state">
      <div className="state__icon" aria-hidden="true" />
      <div className="state__title">{title}</div>
      <p className="state__body">{body}</p>
      <button type="button" className="btn" onClick={onPredict}>
        Predict Demand
      </button>
    </div>
  );
}
