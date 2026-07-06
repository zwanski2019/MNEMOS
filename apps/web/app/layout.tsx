import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { SideNavBar } from "@/components/SideNavBar";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MNEMOS — Mission Control",
  description:
    "Autonomous reconnaissance agent whose memory is the product. Powered by CockroachDB distributed vector memory + AWS Bedrock.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrains.variable}`}>
      <body className="bg-background text-on-surface font-body-sm antialiased h-screen flex overflow-hidden">
        <SideNavBar />
        <div className="ml-nav_rail_width flex-1 flex flex-col h-screen overflow-hidden bg-background">
          {children}
        </div>
      </body>
    </html>
  );
}
