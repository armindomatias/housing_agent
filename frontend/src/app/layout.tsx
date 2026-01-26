import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Rehabify - Estimativa de Remodelação",
  description:
    "Estime o custo de remodelação de imóveis em Portugal usando inteligência artificial. Analise anúncios do Idealista e obtenha estimativas detalhadas.",
  keywords: ["remodelação", "imóveis", "Portugal", "Idealista", "estimativa", "custos"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
