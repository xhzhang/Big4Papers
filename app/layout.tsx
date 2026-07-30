import type { Metadata } from "next";
import "./globals.css";
import "./catalog-insights.css";
import "./team-detail.css";

export const metadata: Metadata = {
  title: "SecAtlas · 网安四大会论文图谱",
  description: "IEEE S&P、ACM CCS、USENIX Security 与 NDSS 论文整理、方向时间线和个人课程选题工具。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

