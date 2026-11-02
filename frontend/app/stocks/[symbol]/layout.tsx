import type { Metadata } from "next";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }): Promise<Metadata> {
  const { symbol } = await params;
  return { title: decodeURIComponent(symbol).toUpperCase() };
}

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
