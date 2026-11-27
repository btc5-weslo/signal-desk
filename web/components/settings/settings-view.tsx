"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Bell, KeyRound, Mail, MessageCircle, Palette, Send, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SideBadge } from "@/components/common/badges";
import { ConfidenceMeter } from "@/components/common/confidence";
import { TenantLogo } from "@/components/shell/tenant-logo";
import { DisclaimerCallout } from "@/components/common/disclaimer";
import { getToken, setToken } from "@/lib/api/client";
import { config } from "@/lib/config";
import { DEFAULT_PREFS, loadPrefs, savePrefs, type Prefs } from "@/lib/prefs";
import { PREVIEW_THEMES, tenantCssVars } from "@/lib/tenant";
import { useTenant } from "@/components/shell/tenant-provider";
import { cn } from "@/lib/utils";

export function SettingsView() {
  const [p, setP] = useState<Prefs>(DEFAULT_PREFS);
  const [saved, setSaved] = useState(false);
  useEffect(() => setP(loadPrefs()), []);
  const set = (patch: Partial<Prefs>) => {
    setSaved(false);
    setP((x) => ({ ...x, ...patch }));
  };
  const ch = (k: keyof Prefs["channels"], v: boolean) => set({ channels: { ...p.channels, [k]: v } });

  return (
    <div className="space-y-4">
      <Card className="bg-surface">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm"><Bell className="size-4 text-brand" /> Alert channels</CardTitle>
          <CardDescription className="text-xs">Saved on this device for now — delivery wiring is pending backend. Every alert carries the approved signal disclaimer.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-line">
          <Channel icon={<Bell className="size-4" />} title="Push notifications" desc="Browser / mobile push when a new signal fires." on={p.channels.push} onChange={(v) => ch("push", v)} />
          <Channel icon={<Mail className="size-4" />} title="Email" on={p.channels.email} onChange={(v) => ch("email", v)}>
            <Input type="email" placeholder="you@example.com" value={p.email} onChange={(e) => set({ email: e.target.value })} className="bg-bg" />
          </Channel>
          <Channel icon={<Send className="size-4" />} title="Telegram" on={p.channels.telegram} onChange={(v) => ch("telegram", v)}>
            <Input placeholder="Chat ID (e.g. 123456789 or @channel)" value={p.telegramChatId} onChange={(e) => set({ telegramChatId: e.target.value })} className="num bg-bg" />
          </Channel>
          <Channel icon={<MessageCircle className="size-4" />} title="Discord webhook" on={p.channels.discord} onChange={(v) => ch("discord", v)}>
            <Input placeholder="https://discord.com/api/webhooks/…" value={p.discordWebhook} onChange={(e) => set({ discordWebhook: e.target.value })} className="num bg-bg" />
          </Channel>
          <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
            <div className="flex items-center gap-3">
              <Label htmlFor="minconf" className="text-xs text-text-muted">Only alert at model score ≥</Label>
              <input id="minconf" type="range" min={0.5} max={0.9} step={0.01} value={p.minConfidence}
                onChange={(e) => set({ minConfidence: Number(e.target.value) })} className="accent-[var(--brand)]" />
              <span className="num text-xs">{p.minConfidence.toFixed(2)}</span>
            </div>
            <Button size="sm" onClick={() => { savePrefs(p); setSaved(true); }}>
              {saved ? <><Check className="size-4" /> Saved</> : "Save preferences"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <TenantPreview />

      <Card className="bg-surface">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm"><KeyRound className="size-4 text-brand" /> API access</CardTitle>
          <CardDescription className="text-xs">Per-tenant API keys and JWT auth.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs text-text-muted">Tenant API key</Label>
            <div className="num mt-1.5 flex items-center justify-between rounded-md border border-dashed border-line bg-bg px-3 py-2 text-xs text-text-muted">
              <span>••••••••••••••••••••</span>
              <span>Key issuance pending backend</span>
            </div>
          </div>
          <TokenField />
          <p className="text-[11px] text-text-muted">API: <span className="num">{config.apiUrl}</span> via same-origin proxy{config.useMock && " · mock mode"}</p>
        </CardContent>
      </Card>

      <DisclaimerCallout k="cryptoFxRisk" />

      <p className="text-xs text-text-muted">
        Re-run onboarding: <Link href="/welcome" className="text-brand hover:underline">/welcome</Link>
      </p>
    </div>
  );
}

function Channel({ icon, title, desc, on, onChange, children }: { icon: ReactNode; title: string; desc?: string; on: boolean; onChange: (v: boolean) => void; children?: ReactNode }) {
  return (
    <div className="py-3.5 first:pt-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid size-8 place-items-center rounded-md border border-line bg-bg text-text-muted">{icon}</span>
          <div>
            <div className="text-sm">{title}</div>
            {desc && <div className="text-xs text-text-muted">{desc}</div>}
          </div>
        </div>
        <Switch checked={on} onCheckedChange={onChange} aria-label={title} />
      </div>
      {on && children && <div className="mt-3 pl-11">{children}</div>}
    </div>
  );
}

function TokenField() {
  const [v, setV] = useState("");
  const [has, setHas] = useState(false);
  useEffect(() => setHas(!!getToken()), []);
  return (
    <div>
      <Label className="text-xs text-text-muted">Session token (JWT, dev)</Label>
      <div className="mt-1.5 flex gap-2">
        <Input type="password" placeholder={has ? "Token set — paste to replace" : "Paste a bearer token"} value={v} onChange={(e) => setV(e.target.value)} className="num bg-bg" />
        <Button variant="secondary" size="sm" onClick={() => { setToken(v || null); setHas(!!v); setV(""); }}>{v ? "Set" : "Clear"}</Button>
      </div>
    </div>
  );
}

function TenantPreview() {
  const current = useTenant();
  const options = [current, ...PREVIEW_THEMES.filter((p) => p.id !== current.id)];
  const [id, setId] = useState(current.id);
  const t = options.find((o) => o.id === id) ?? current;
  return (
    <Card className="bg-surface">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm"><Palette className="size-4 text-brand" /> White-label theme preview</CardTitle>
        <CardDescription className="text-xs">Branding comes from GET /v1/tenant/config (by host) and is applied as CSS variables. Active: <span className="num">{current.name}</span>.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-[200px_1fr]">
        <div className="flex flex-col gap-1.5">
          {options.map((x) => (
            <button key={x.id} onClick={() => setId(x.id)}
              className={cn("flex items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs", id === x.id ? "border-brand/60 bg-surface-2" : "border-line hover:bg-surface-2/60")}>
              <span className="flex gap-0.5">
                {[x.colors.accent, x.colors.long, x.colors.short].map((c) => <span key={c} className="size-3 rounded-full" style={{ background: c }} />)}
              </span>
              {x.name}
            </button>
          ))}
        </div>
        <div style={tenantCssVars(t) as CSSProperties} className="rounded-xl border border-line bg-bg p-4 text-text">
          <div className="mb-3 flex items-center gap-2">
            <TenantLogo tenant={t} size={22} />
            <span className="text-sm font-semibold">{t.name}</span>
          </div>
          <div className="rounded-lg border border-line bg-surface p-3">
            <div className="flex items-center gap-2"><span className="num font-semibold">BTC/USDT</span><SideBadge side="long" /></div>
            <div className="mt-2 flex items-center justify-between">
              <ConfidenceMeter value={0.66} />
              <span className="rounded-md bg-brand px-2 py-1 text-[11px] font-medium text-brand-text">Primary action</span>
            </div>
          </div>
          <p className="mt-2 text-[10px] text-text-muted">Preview only — sample levels, not a live signal.</p>
        </div>
      </CardContent>
    </Card>
  );
}
