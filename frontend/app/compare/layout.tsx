import type { Metadata } from "next";

export const metadata: Metadata = { title: "비교" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
