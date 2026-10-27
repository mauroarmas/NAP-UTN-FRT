FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS deps

WORKDIR /app

COPY frontend/package*.json ./

RUN npm ci

# --- Etapa de desarrollo: dev server de Vite con HMR ---
FROM deps AS dev

WORKDIR /app

COPY frontend ./

EXPOSE 5173

CMD ["npm", "run", "dev"]

# --- Etapa de build de producción ---
FROM deps AS builder

COPY frontend ./

RUN npm run build

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS preview

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

EXPOSE 5173

CMD ["serve", "-s", "dist", "-l", "5173"]

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS production

USER root
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY infra/proxy/nginx.conf /etc/nginx/templates/default.conf.template
USER 101:101
EXPOSE 8080 8443
