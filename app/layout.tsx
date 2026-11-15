import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GoJob",
  description: "Profile health check, JD matching, tailored follow-ups and an application tracker.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@500;600&family=Noto+Sans+TC:wght@400;500;700&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  );
}
