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

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ДЛЯ NEXT BUILD ===
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_BASE_URL
ARG NEXT_PUBLIC_STRAPI_URL
ARG NEXT_PUBLIC_CRM_API_URL

# Делаем их доступными в ENV (обязательно!)
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_BASE_URL=${NEXT_PUBLIC_BASE_URL}
ENV NEXT_PUBLIC_STRAPI_URL=${NEXT_PUBLIC_STRAPI_URL}
ENV NEXT_PUBLIC_CRM_API_URL=${NEXT_PUBLIC_CRM_API_URL}

# Копируем node_modules и код
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Добавляем проверку (опционально, для логов)
RUN echo "Building with API_URL=$NEXT_PUBLIC_API_URL" && \
    if [ -z "$NEXT_PUBLIC_API_URL" ]; then echo "ERROR: NEXT_PUBLIC_API_URL not set!" && exit 1; fi

# Сборка Next.js (теперь видит переменные!)
RUN npm run build


# ---------------------
# Финальный рантайм-образ
# ---------------------
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3001

# Переменные на runtime (необязательно, но для логов)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_BASE_URL
ARG NEXT_PUBLIC_STRAPI_URL
ARG NEXT_PUBLIC_CRM_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_BASE_URL=${NEXT_PUBLIC_BASE_URL}
ENV NEXT_PUBLIC_STRAPI_URL=${NEXT_PUBLIC_STRAPI_URL}
ENV NEXT_PUBLIC_CRM_API_URL=${NEXT_PUBLIC_CRM_API_URL}

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Копируем артефакты
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3001/ || exit 1

CMD ["node", "server.js"]