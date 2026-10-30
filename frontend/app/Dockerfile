FROM node:24-alpine AS builder

ENV NODE_ENV=production

WORKDIR /app

RUN corepack enable && corepack prepare "pnpm@12.6.0" --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginxinc/nginx-unprivileged:alpine-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/straightchlorine/wke"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="wke-web"
LABEL org.opencontainers.image.description="Wikipedia Knowledge Explorer - React SPA served by nginx"

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# same uid the upstream image sets
USER 101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
