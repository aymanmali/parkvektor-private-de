"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Car,
  LayoutDashboard,
  MonitorSmartphone,
  Scale,
  ShieldCheck,
  Ticket,
  Zap,
} from "lucide-react";
import { DICT, Locale } from "@/lib/i18n";

export function Navbar({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const pathname = usePathname();
  const otherLocale: Locale = locale === "de" ? "en" : "de";
  const switchedPath = pathname.replace(`/${locale}`, `/${otherLocale}`);

  const links = [
    { href: `/${locale}/pay`, label: t.navPay, icon: Car, active: pathname.includes("/pay") },
    { href: `/${locale}/autopay`, label: t.navAutoPay, icon: Zap, active: pathname.includes("/autopay") },
    { href: `/${locale}/kiosk`, label: t.navKiosk, icon: MonitorSmartphone, active: pathname.includes("/kiosk") },
    { href: `/${locale}/validate`, label: t.navValidate, icon: Ticket, active: pathname.includes("/validate") },
    { href: `/${locale}/dispute`, label: t.navDispute, icon: Scale, active: pathname.includes("/dispute") },
    { href: `/${locale}/admin`, label: t.navAdmin, icon: LayoutDashboard, active: pathname.includes("/admin") },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-4 py-2.5 sm:px-6">
        <Link href={`/${locale}/pay`} className="flex shrink-0 items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-emerald-500 text-white shadow-lg shadow-blue-900/40">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="hidden lg:block">
            <div className="flex items-center gap-1.5 text-sm font-semibold tracking-tight text-white">
              <span>ParkVektor DE</span>
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-300 ring-1 ring-emerald-500/30">
                DSGVO
              </span>
            </div>
            <p className="text-[11px] text-slate-400">{t.brandSubtitle}</p>
          </div>
        </Link>

        <div className="flex min-w-0 items-center gap-2">
          <nav className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {links.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                    item.active
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <Link
            href={switchedPath}
            className="flex shrink-0 items-center rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-blue-500 hover:text-white"
            title="Switch language / Sprache wechseln"
          >
            <span className={locale === "de" ? "text-blue-400" : "text-slate-500"}>DE</span>
            <span className="mx-1 text-slate-600">|</span>
            <span className={locale === "en" ? "text-blue-400" : "text-slate-500"}>EN</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
