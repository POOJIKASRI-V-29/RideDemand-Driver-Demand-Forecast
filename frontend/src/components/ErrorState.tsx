interface Props {
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: Props) {
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon state__icon--error" aria-hidden="true">
        !
      </div>
      <div className="state__title">Unable to generate forecast</div>
      <p className="state__body">The request to the RideDemand API did not succeed.</p>
      <span className="state__detail">{message}</span>
      <button type="button" className="btn btn--dark" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
