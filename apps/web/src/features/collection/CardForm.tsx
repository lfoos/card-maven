import { useId, useState, type FormEvent } from "react";
import { NO_ERRORS, toFormErrors, type FormErrors } from "../../api/fieldErrors";
import type { NewItem } from "../../api/types";
import { Field } from "../../components/Field";
import { SPORT_OPTIONS } from "../../lib/format";
import { GRADERS, toNewItem, validate, type CardFormValues } from "./cardFormModel";
import { usePlayerSuggestions, useSetSuggestions } from "./useSuggestions";

interface CardFormProps {
  initial: CardFormValues;
  submitLabel: string;
  onSubmit: (body: NewItem) => Promise<unknown>;
  onCancel?: () => void;
}

export function CardForm({ initial, submitLabel, onSubmit, onCancel }: CardFormProps) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const [submitting, setSubmitting] = useState(false);
  const setsListId = useId();
  const playersListId = useId();
  const sets = useSetSuggestions(values.set_name, values.sport, values.year);
  const players = usePlayerSuggestions(values.players, values.sport);

  function set<K extends keyof CardFormValues>(key: K, value: CardFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  const text = (key: keyof CardFormValues) => ({
    value: values[key] as string,
    onChange: (e: { target: { value: string } }) => set(key, e.target.value as never),
  });
  const err = (loc: string) => errors.fields[loc];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const local = validate(values);
    if (Object.keys(local).length > 0) {
      setErrors({ fields: local, form: "Please fix the highlighted fields." });
      return;
    }
    setSubmitting(true);
    setErrors(NO_ERRORS);
    try {
      await onSubmit(toNewItem(values));
    } catch (error) {
      setErrors(toFormErrors(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
      {errors.form ? (
        <div role="alert" className="notice notice--error">
          {errors.form}
        </div>
      ) : null}

      <fieldset>
        <legend>Card</legend>
        <div className="form-grid">
          <Field label="Sport" error={err("card.sport")}>
            {(a) => (
              <select {...a} {...text("sport")}>
                {SPORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Year" error={err("card.year")}>
            {(a) => <input {...a} {...text("year")} inputMode="numeric" />}
          </Field>
          <Field label="Brand" error={err("card.brand")}>
            {(a) => <input {...a} {...text("brand")} placeholder="Bowman" autoComplete="off" />}
          </Field>
          <Field label="Set" error={err("card.set_name")} className="field--wide">
            {(a) => (
              <>
                <input
                  {...a}
                  {...text("set_name")}
                  list={setsListId}
                  placeholder="Bowman Chrome"
                  autoComplete="off"
                />
                <datalist id={setsListId}>
                  {(sets.data ?? []).map((s) => (
                    <option key={s.id} value={s.name}>{`${s.year} · ${s.brand}`}</option>
                  ))}
                </datalist>
              </>
            )}
          </Field>
          <Field label="Card #" error={err("card.card_number")}>
            {(a) => (
              <input {...a} {...text("card_number")} placeholder="CPA-JW" autoComplete="off" />
            )}
          </Field>
          <Field label="Card name" error={err("card.name")} className="field--wide">
            {(a) => <input {...a} {...text("name")} placeholder="JJ Wetherholt" />}
          </Field>
          <Field
            label="Players"
            error={err("card.players")}
            hint="Comma-separated for multi-player cards"
            className="field--wide"
          >
            {(a) => (
              <>
                <input {...a} {...text("players")} list={playersListId} autoComplete="off" />
                <datalist id={playersListId}>
                  {(players.data ?? []).map((p) => (
                    <option key={p.id} value={p.full_name} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
          <Field label="Team" error={err("card.team")}>
            {(a) => <input {...a} {...text("team")} />}
          </Field>
          <Field label="Subset" error={err("card.subset")} hint="e.g. Chrome Prospect Autographs">
            {(a) => <input {...a} {...text("subset")} />}
          </Field>
          <Field label="Parallel" error={err("card.parallel.name")} hint="Leave blank for base">
            {(a) => <input {...a} {...text("parallel_name")} placeholder="Gold Refractor" />}
          </Field>
          <Field label="Print run" error={err("card.parallel.print_run")} hint="The /50 in 12/50">
            {(a) => (
              <input
                {...a}
                {...text("print_run")}
                inputMode="numeric"
                disabled={!values.parallel_name.trim()}
              />
            )}
          </Field>
        </div>
        <div className="checks">
          {(
            [
              ["is_rookie", "Rookie"],
              ["is_autograph", "Autograph"],
              ["is_memorabilia", "Memorabilia"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="check">
              <input
                type="checkbox"
                checked={values[key]}
                onChange={(e) => set(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Your copy</legend>
        <div className="form-grid">
          <Field label="Condition" error={err("condition")}>
            {(a) => (
              <select
                {...a}
                value={values.condition}
                onChange={(e) => set("condition", e.target.value as CardFormValues["condition"])}
              >
                <option value="raw">Raw</option>
                <option value="graded">Graded</option>
              </select>
            )}
          </Field>
          {values.condition === "graded" ? (
            <>
              <Field label="Grader" error={err("grader")}>
                {(a) => (
                  <select {...a} {...text("grader")}>
                    {GRADERS.map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label="Grade" error={err("grade")}>
                {(a) => <input {...a} {...text("grade")} inputMode="decimal" placeholder="10" />}
              </Field>
              <Field label="Cert #" error={err("cert_number")}>
                {(a) => <input {...a} {...text("cert_number")} />}
              </Field>
            </>
          ) : null}
          <Field label="Serial #" error={err("serial_number")} hint="The 12 in 12/50">
            {(a) => <input {...a} {...text("serial_number")} inputMode="numeric" />}
          </Field>
          <Field
            label="Price paid (USD)"
            error={err("purchase_price.amount") ?? err("purchase_price")}
          >
            {(a) => (
              <input {...a} {...text("purchase_price")} inputMode="decimal" placeholder="49.99" />
            )}
          </Field>
          <Field label="Acquired" error={err("acquired_on")}>
            {(a) => <input {...a} {...text("acquired_on")} type="date" />}
          </Field>
          <Field label="Notes" error={err("notes")} className="field--full">
            {(a) => <textarea {...a} {...text("notes")} rows={3} maxLength={2000} />}
          </Field>
        </div>
      </fieldset>

      <div className="form-actions">
        {onCancel ? (
          <button type="button" className="button button--quiet" onClick={onCancel}>
            Cancel
          </button>
        ) : null}
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
