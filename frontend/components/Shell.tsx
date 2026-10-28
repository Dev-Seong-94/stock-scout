"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useUpColor } from "@/lib/storage";

const LINKS = [
  { href: "/", label: "대시보드" },
  { href: "/screener", label: "스크리너" },
  { href: "/macro", label: "거시·정세" },
  { href: "/watchlist", label: "관심종목" },
];

function Logo() {
  // A magnifier over a rising line: "finding" rather than "trading".
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 16l4-4 3 3 5-6" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="15" cy="10" r="6" stroke="currentColor" strokeWidth="1.8" />
      <path d="M19.5 14.5L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [upColor, setUpColor] = useUpColor();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href) || (href === "/screener" && pathname.startsWith("/stocks"));

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <Logo />
          <span>Stock Scout</span>
        </Link>
        <nav className="nav" aria-label="주요 화면">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={isActive(l.href) ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar__foot">
          <label>
            <span className="sr-only">상승 색상</span>
            <select className="input small" value={upColor} onChange={(e) => setUpColor(e.target.value as "red" | "green")}>
              <option value="red">상승 빨강 · 하락 파랑</option>
              <option value="green">상승 초록 · 하락 빨강</option>
            </select>
          </label>
          <p>투자 추천이 아닌 개인 리서치 도구예요. 데이터는 지연될 수 있어요.</p>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
