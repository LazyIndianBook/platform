"use client";

// The print run of one title in one panel (POST reports/print-run/): the newsvendor's sum with the net price, the print
// cost and the salvage as editable fields, worked out again by the API each time (the critical ratio, the demand at
// that percentile of the newest forecast, less the copies in stock and on order) and drawn with its range, its method
// and how the last backtest went. Nothing is stored: the nightly advice above is unchanged. It is worked out once on
// opening with the nightly inputs, so the panel is never empty; a forecast that has not beaten the seasonal naive is
// labelled untested.
import { useEffect, useRef, useState } from "react";

import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { type PrintRun, recomputePrintRun } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { backtestLine } from "./insights";
import { count, rupees } from "./numbers";

type Inputs = { net_price: string; unit_cost: string; salvage: string };

const MONEY = /^\d{1,8}(\.\d{1,2})?$/;

/** The inputs typed, checked before anything is sent: rupees, at most two places, each there (the API checks again). */
export function inputProblems(values: Inputs): Partial<Record<keyof Inputs, string>> {
  const words = copy.reports.forecasts;
  const found: Partial<Record<keyof Inputs, string>> = {};
  for (const name of ["net_price", "unit_cost", "salvage"] as const)
    if (!MONEY.test(values[name].trim())) found[name] = words.moneyProblem;
  return found;
}

export function Result({ result }: { result: PrintRun }) {
  const words = copy.reports.forecasts;
  return (
    <div className="flex flex-col gap-4" role="status" aria-label={words.resultLabel}>
      <p className="m-0 text-[15px]">{words.ratioSentence(result.critical_ratio.toFixed(4), result.percentile)}</p>
      {result.recommended_quantity === null ? (
        <p className="m-0 text-[15px] font-semibold">{result.note || words.noForecastNote}</p>
      ) : (
        <>
          <p className="m-0 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="numeral text-[32px]">{count(result.recommended_quantity)}</span>
            <span className="text-[15px] font-semibold">{words.printNow}</span>
            {result.shown ? null : <StatusChip tone="waiting">{words.untested}</StatusChip>}
          </p>
          <dl className="m-0 grid max-w-[40rem] grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 text-[15px]">
            <dt>{words.targetSentence(result.percentile)}</dt>
            <dd className="m-0 text-right font-mono">{count(result.target_quantity)}</dd>
            <dt>{words.supplySentence}</dt>
            <dd className="m-0 text-right font-mono">{count(result.supply)}</dd>
            {result.range ? (
              <>
                <dt>{words.rangeSentence(result.range.weeks)}</dt>
                <dd className="m-0 text-right font-mono">
                  {count(result.range.p10)} · {count(result.range.p50)} · {count(result.range.p90)}
                </dd>
              </>
            ) : null}
          </dl>
          {result.note ? <p className="m-0 text-[15px] text-muted-foreground">{result.note}</p> : null}
        </>
      )}
      <p className="m-0 max-w-[60ch] text-sm text-muted-foreground">
        {result.method ? words.methodSentence(result.method) : null}
        {result.data_as_of ? ` ${words.forecastAsOf(formatDateTime(result.data_as_of))}` : null}
      </p>
      <p className="m-0 max-w-[60ch] text-sm text-muted-foreground">{backtestLine(result)}</p>
    </div>
  );
}

export function PrintRunPanel({ product, title, inputs }: { product: string; title: string; inputs: Inputs }) {
  const words = copy.reports.forecasts;
  const [values, setValues] = useState<Inputs>(inputs);
  const [result, setResult] = useState<PrintRun | null>(null);
  const [problems, setProblems] = useState<Partial<Record<keyof Inputs, string>>>({});
  const { run, busy, error } = useAction();
  const work = (typed: Inputs) => run(async () => setResult(await recomputePrintRun({ product, ...trimmed(typed) })));
  const first = useRef(work);
  useEffect(() => {
    first.current = work;
  });
  useEffect(() => {
    void first.current(inputs); // worked out once on opening, with the nightly inputs
  }, [inputs]);

  const change = (name: keyof Inputs) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setValues((current) => ({ ...current, [name]: event.target.value }));

  return (
    <form
      noValidate
      aria-label={words.panelLabel(title)}
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        const found = inputProblems(values);
        setProblems(found);
        if (Object.keys(found).length === 0) void work(values);
      }}
    >
      <ErrorSummary error={error} />
      <FormGrid className="[--min:12rem]">
        <Field
          id="print-net"
          label={words.netPrice}
          help={words.netPriceHelp}
          error={problems.net_price ?? fieldError(error, "net_price")}
        >
          <Input name="net_price" inputMode="decimal" value={values.net_price} onChange={change("net_price")} />
        </Field>
        <Field
          id="print-cost"
          label={words.unitCost}
          help={words.unitCostHelp}
          error={problems.unit_cost ?? fieldError(error, "unit_cost")}
        >
          <Input name="unit_cost" inputMode="decimal" value={values.unit_cost} onChange={change("unit_cost")} />
        </Field>
        <Field
          id="print-salvage"
          label={words.salvage}
          help={words.salvageHelp}
          error={problems.salvage ?? fieldError(error, "salvage")}
        >
          <Input name="salvage" inputMode="decimal" value={values.salvage} onChange={change("salvage")} />
        </Field>
      </FormGrid>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" busy={busy}>
          {words.workItOut}
        </Button>
        <span className="text-sm text-muted-foreground">
          {words.nightlyInputs(rupees(inputs.net_price), rupees(inputs.unit_cost), rupees(inputs.salvage))}
        </span>
      </div>
      {result ? <Result result={result} /> : busy ? <p className="m-0 text-[15px]">{copy.common.working}</p> : null}
    </form>
  );
}

const trimmed = (typed: Inputs): Inputs => ({
  net_price: typed.net_price.trim(),
  unit_cost: typed.unit_cost.trim(),
  salvage: typed.salvage.trim(),
});
