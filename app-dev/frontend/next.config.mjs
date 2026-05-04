/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",

  async headers() {
    const isDev = process.env.NODE_ENV === "development";
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: getCSP(isDev),
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), microphone=(), camera=()",
          },
          ...(!isDev
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000; includeSubDomains",
                },
              ]
            : []),
        ],
      },
    ];
  },

  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "strapi.pticasinicafamily.ru",
        pathname: "/uploads/**",
      },
      {
        protocol: "https",
        hostname: "maps.geoapify.com",
      },
      {
        protocol: "https",
        hostname: "api-maps.yandex.ru",
      },
      {
        protocol: "https",
        hostname: "*.maps.yandex.net",
      },
      {
        protocol: "https",
        hostname: "yastatic.net",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
      },
    ],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    qualities: [40, 50, 60, 75, 85, 90, 95],
  },

  transpilePackages: ["@pbe/react-yandex-maps"],

  webpack: (config, { isServer, dev }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        path: false,
      };
    }

    if (!dev && !isServer) {
      config.optimization.splitChunks = {
        chunks: "all",
        cacheGroups: {
          default: false,
          vendors: false,
          commons: {
            name: "commons",
            minChunks: 2,
            reuseExistingChunk: true,
          },
          yandexMaps: {
            test: /[\\/]node_modules[\\/](@pbe[\\/]react-yandex-maps|yandex-maps)[\\/]/,
            name: "yandex-maps",
            priority: 20,
            reuseExistingChunk: true,
          },
        },
      };
    }

    return config;
  },
};

/* =========================
   CSP GENERATOR
   ========================= */

function getCSP(isDev) {
  const baseCSP = [
    "default-src 'self' blob: data:;",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org https://*.telegram.org https://api-maps.yandex.ru https://*.maps.yandex.net https://yastatic.net;",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://api-maps.yandex.ru https://yastatic.net;",
    "font-src 'self' https://fonts.gstatic.com https://yastatic.net;",
    "img-src 'self' blob: data: https://strapi.pticasinicafamily.ru https://*.geoapify.com https://api-maps.yandex.ru https://*.maps.yandex.net https://yastatic.net;",
    "connect-src 'self' https://server.pticasinicafamily.ru wss://server.pticasinicafamily.ru https://strapi.pticasinicafamily.ru https://api-maps.yandex.ru https://*.maps.yandex.net https://yastatic.net",
    "frame-src 'self' https://api-maps.yandex.ru https://telegram.org https://strapi.pticasinicafamily.ru;",
    "child-src 'self' blob: https://api-maps.yandex.ru;",
  ];

  if (isDev) {
    baseCSP[5] += " ws://localhost:* wss://localhost:* http://localhost:*";

    const backendUrl =
      process.env.NEXT_PUBLIC_CRM_API_URL || "http://localhost:3001";

    if (backendUrl.startsWith("http://")) {
      baseCSP[5] += ` ${backendUrl} ${backendUrl.replace("http://", "ws://")}`;
    } else if (backendUrl.startsWith("https://")) {
      baseCSP[5] += ` ${backendUrl} ${backendUrl.replace(
        "https://",
        "wss://",
      )}`;
    }
  }

  baseCSP[5] += " ws://server.pticasinicafamily.ru;";

  return baseCSP.join(" ");
}

export default nextConfig;
