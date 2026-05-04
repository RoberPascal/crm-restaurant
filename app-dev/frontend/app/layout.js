// app/layout.jsx
import "./globals.scss";
import TelegramAppWrapper from "@/components/TelegramAppWrapper";

export default function RootLayout({ children }) {
  return (
    <html lang="ru" suppressHydrationWarning>
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
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
      </head>
      <body suppressHydrationWarning>
        <TelegramAppWrapper>{children}</TelegramAppWrapper>
      </body>
    </html>
  );
}

export const metadata = {
  title: "Chain Restaurants",
  description: "Сеть уютных баров в Москве",
};
