FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS=60
ENV NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS=${NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS}
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node","server.js"]
