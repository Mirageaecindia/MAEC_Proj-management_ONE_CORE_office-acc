# MAEC ProManage web: builds the React app, then Caddy serves it, proxies /api
# to the backend and handles HTTPS. Built and run by the root docker-compose.yml.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Empty = same origin: the browser calls /api on this server, and Caddy forwards it.
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
