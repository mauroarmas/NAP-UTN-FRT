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

FROM caddy:2-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5 AS production

# El binario oficial trae la capacidad de enlazar puertos bajos; el proxy usa 8080/8443 y corre sin capacidades.
RUN setcap -r /usr/bin/caddy
COPY --from=builder /app/dist /usr/share/caddy
COPY infra/proxy/Caddyfile /etc/caddy/Caddyfile
USER 101:101
EXPOSE 8080 8443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
