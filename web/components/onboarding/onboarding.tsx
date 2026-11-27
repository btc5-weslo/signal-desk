"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Bell, Check, Mail, MessageCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { TenantLogo } from "@/components/shell/tenant-logo";
import { Disclaimer, TenantExtraDisclaimers } from "@/components/common/disclaimer";
import { DEFAULT_PREFS, loadPrefs, savePrefs, type Prefs } from "@/lib/prefs";
import type { TenantTheme } from "@/lib/tenant";
import { ASSET_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ASSET_CLASSES, TIMEFRAMES, type AssetClass, type Timeframe } from "@/lib/types/signal";

const STEPS = ["Markets", "Timeframes", "Alerts", "Risk"];

const MARKET_DESC: Record<AssetClass, string> = {
  crypto: "BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT",
  equity: "SPY, QQQ, AAPL, MSFT, NVDA, TSLA, AMZN, META",
  fx: "EUR/USD, GBP/USD, USD/JPY, AUD/USD",
};
const TF_DESC: Record<Timeframe, string> = { "15m": "Intraday scalps", "1h": "Intraday swings", "4h": "Multi-day swings", "1d": "Position trades" };

function toggle<T>(arr: T[], v: T) {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

export function Onboarding({ tenant }: { tenant: TenantTheme }) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [p, setP] = useState<Prefs>(DEFAULT_PREFS);
  const [ack, setAck] = useState(false);
  useEffect(() => setP(loadPrefs()), []);

  const canNext = [p.markets.length > 0, p.timeframes.length > 0, true, ack][step];
  const finish = () => {
    savePrefs({ ...p, riskAcknowledgedAt: new Date().toISOString() });
    router.push("/");
  };

  return (
    <div className="surface-glow flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl">
        <div className="mb-8 flex items-center gap-2.5">
          <TenantLogo tenant={tenant} size={30} />
          <span className="text-lg font-semibold tracking-tight">{tenant.name}</span>
        </div>

        <ol className="mb-6 flex gap-2">
          {STEPS.map((s, i) => (
            <li key={s} className="flex-1">
              <div className={cn("h-1 rounded-full", i <= step ? "bg-brand" : "bg-surface-2")} />
              <div className={cn("mt-1.5 text-[11px]", i === step ? "text-text" : "text-text-muted")}>{i + 1}. {s}</div>
            </li>
          ))}
        </ol>

        <div className="rounded-2xl border border-line bg-surface p-6">
          {step === 0 && (
            <Step title="Which markets do you trade?" sub="You can change this anytime in Settings.">
              {ASSET_CLASSES.map((a) => (
                <Choice key={a} on={p.markets.includes(a)} onClick={() => setP({ ...p, markets: toggle(p.markets, a) })} title={ASSET_LABEL[a]} desc={MARKET_DESC[a]} />
              ))}
            </Step>
          )}
          {step === 1 && (
            <Step title="Pick your timeframes" sub="Lower timeframes produce more signals; some lack enough history to be validated out-of-sample.">
              <div className="grid grid-cols-2 gap-2">
                {TIMEFRAMES.map((t) => (
                  <Choice key={t} on={p.timeframes.includes(t)} onClick={() => setP({ ...p, timeframes: toggle(p.timeframes, t) })} title={t} desc={TF_DESC[t]} mono />
                ))}
              </div>
            </Step>
          )}
          {step === 2 && (
            <Step title="How should we alert you?" sub="Connect details later in Settings.">
              {([
                ["push", "Push notifications", Bell],
                ["email", "Email", Mail],
                ["telegram", "Telegram", Send],
                ["discord", "Discord webhook", MessageCircle],
              ] as const).map(([k, label, Icon]) => (
                <Choice key={k} on={p.channels[k]} onClick={() => setP({ ...p, channels: { ...p.channels, [k]: !p.channels[k] } })} title={label} icon={<Icon className="size-4" />} />
              ))}
            </Step>
          )}
          {step === 3 && (
            <Step title="Before you start" sub="Please read and acknowledge.">
              <div className="space-y-2 rounded-lg border border-line bg-bg/60 p-4 text-xs leading-relaxed text-text-muted">
                <Disclaimer k="footer" className="text-text" />
                <Disclaimer k="cryptoFxRisk" />
                <Disclaimer k="signal" />
                <TenantExtraDisclaimers />
                <p>Signals marked “Unvalidated” lack sufficient out-of-sample history for that market and timeframe.</p>
              </div>
              <label className="flex cursor-pointer items-start gap-2.5 text-sm">
                <Checkbox checked={ack} onCheckedChange={(v) => setAck(v === true)} className="mt-0.5" />
                I understand these signals are not financial advice and I am solely responsible for my trading decisions.
              </label>
            </Step>
          )}

          <div className="mt-6 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => setStep((s) => s - 1)} disabled={step === 0}>Back</Button>
            {step < 3 ? (
              <Button size="sm" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Continue</Button>
            ) : (
              <Button size="sm" onClick={finish} disabled={!ack}>Go to dashboard</Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Step({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <p className="mt-1 mb-5 text-sm text-text-muted">{sub}</p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function Choice({ on, onClick, title, desc, icon, mono }: { on: boolean; onClick: () => void; title: string; desc?: string; icon?: ReactNode; mono?: boolean }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={cn("flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors", on ? "border-brand/60 bg-brand/8" : "border-line hover:bg-surface-2/60")}>
      {icon && <span className="text-text-muted">{icon}</span>}
      <div className="flex-1">
        <div className={cn("text-sm font-medium", mono && "num")}>{title}</div>
        {desc && <div className="text-xs text-text-muted">{desc}</div>}
      </div>
      <span className={cn("grid size-5 place-items-center rounded-full border", on ? "border-brand bg-brand text-brand-text" : "border-line")}>
        {on && <Check className="size-3" />}
      </span>
    </button>
  );
}
