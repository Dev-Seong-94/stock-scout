import type { Metadata } from "next";
import { IBM_Plex_Sans_KR } from "next/font/google";

import Shell from "@/components/Shell";

import "./globals.css";

const plex = IBM_Plex_Sans_KR({
  variable: "--font-plex-kr",
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "Stock Scout",
  description: "거시 환경을 보면서 지표로 종목을 좁혀 가는 개인 리서치 도구",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className={plex.variable} data-up="red">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
