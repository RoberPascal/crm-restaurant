# ---------------------
# Базовый образ
# ---------------------
FROM node:20-alpine AS base

# Устанавливаем зависимости
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Копируем lock-файлы и устанавливаем зависимости
COPY package.json yarn.lock* package-lock.json* pnpm-lock.yaml* ./
RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci --legacy-peer-deps; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm i --frozen-lockfile; \
  else echo "Lockfile not found." && exit 1; \
  fi

# ---------------------
# Сборка проекта
# ---------------------
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# === ВСЕ NEXT_PUBLIC ПЕРЕМЕННЫЕ ДЛЯ СБОРКИ ===
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_BASE_URL
ARG NEXT_PUBLIC_STRAPI_URL
ARG NEXT_PUBLIC_STRAPI_BASE_URL
ARG NEXT_PUBLIC_CRM_API_URL

# Делаем их доступными во время сборки
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_BASE_URL=${NEXT_PUBLIC_BASE_URL}
ENV NEXT_PUBLIC_STRAPI_URL=${NEXT_PUBLIC_STRAPI_URL}
ENV NEXT_PUBLIC_STRAPI_BASE_URL=${NEXT_PUBLIC_STRAPI_BASE_URL}
ENV NEXT_PUBLIC_CRM_API_URL=${NEXT_PUBLIC_CRM_API_URL}

# Логируем значения для отладки
RUN echo "=== Building with environment variables ===" && \
    echo "NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL" && \
    echo "NEXT_PUBLIC_BASE_URL=$NEXT_PUBLIC_BASE_URL" && \
    echo "NEXT_PUBLIC_STRAPI_URL=$NEXT_PUBLIC_STRAPI_URL" && \
    echo "NEXT_PUBLIC_STRAPI_BASE_URL=$NEXT_PUBLIC_STRAPI_BASE_URL" && \
    echo "NEXT_PUBLIC_CRM_API_URL=$NEXT_PUBLIC_CRM_API_URL"

# Сборка проекта Next.js
RUN npm run build

# ---------------------
# Финальный рантайм-образ
# ---------------------
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Копируем нужные файлы из builder
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1

# Запуск standalone-сервера
CMD ["node", "server.js"]