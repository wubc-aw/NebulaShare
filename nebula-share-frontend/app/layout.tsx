import type { Metadata, Viewport } from 'next'
import { ThemeProvider } from '@/components/theme-provider'
import { AppShell } from '@/components/app-shell'
import './globals.css'

export const metadata: Metadata = {
  title: 'Nebula',
  description: 'AW 的私人指挥中心',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: '#0a0a0f',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className="bg-background">
      <body className="font-sans antialiased min-h-screen">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange themes={["dark", "light", "vivid", "tron"]}>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  )
}
