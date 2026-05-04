import "./globals.css";
import ErrorBoundary from "@/components/ErrorBoundary/ErrorBoundary";

export const metadata = {
  title: "Птица CRM",
  description: "Система управления бронированиями ресторана Птица",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@200..700&family=Oswald:wght@200..700&family=Playfair+Display:wght@200..700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
