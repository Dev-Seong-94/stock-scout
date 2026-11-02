import type { Metadata } from "next";

export const metadata: Metadata = { title: "거시·정세" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
