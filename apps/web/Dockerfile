# syntax=docker/dockerfile:1.7
# Static build served by unprivileged nginx. Build context: apps/web
FROM node:22-slim AS build
# Install the exact pnpm from package.json#packageManager (no corepack key fetches).
RUN npm install -g pnpm@10.28.0
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG VITE_API_BASE_URL
ARG VITE_OIDC_AUTHORITY
ARG VITE_OIDC_CLIENT_ID
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
