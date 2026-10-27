import { useId, type ReactNode } from "react";

interface FieldProps {
  label: string;
  error?: string | undefined;
  hint?: string;
  children: (props: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby"?: string;
  }) => ReactNode;
  className?: string;
}

/** Label + control + error/hint, wired up for screen readers. */
export function Field({ label, error, hint, children, className }: FieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;
  return (
    <div className={`field${error ? " field--error" : ""}${className ? ` ${className}` : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children({
        id,
        "aria-invalid": Boolean(error),
        ...(message ? { "aria-describedby": messageId } : {}),
      })}
      {message ? (
        <p id={messageId} className={error ? "field__error" : "field__hint"}>
          {message}
        </p>
      ) : null}
    </div>
  );
}
