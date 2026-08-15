FROM node:20-alpine AS deps

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

FROM node:20-alpine

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

EXPOSE 5173

CMD ["serve", "-s", "dist", "-l", "5173"]
