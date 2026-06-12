# ── Stage 1: build ──
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build-time API base (rewrite proxy target); can be overridden at build time
ARG NEXT_PUBLIC_API_BASE_URL=http://backend:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# Ensure public dir exists for COPY in runner stage
RUN mkdir -p /app/public

# ── Stage 2: production ──
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Next.js standalone already includes a minimal server.js
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# public directory is optional (may not exist in all projects)
COPY --from=builder /app/public ./public/

EXPOSE 3000
ENV PORT=3000 \
    HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
