# Multi-stage: the build stage carries the full node_modules + dev dependencies needed to
# run `next build`; the final image carries only what next.config.mjs's `output:
# "standalone"` traced as actually required at runtime, which is a small fraction of that.
FROM node:22-slim AS deps
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /srv
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
# Next inlines NEXT_PUBLIC_* at BUILD time -- passed as a build arg so the value baked into
# this image is the one docker-compose.yml or the build command actually provides, not
# whatever happens to be in the shell that ran `docker build`.
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build

FROM node:22-slim AS run
WORKDIR /srv
ENV NODE_ENV=production
RUN useradd --create-home --uid 10001 yaadhum
# No public/ in this project (no static assets served that way) -- next build's own
# standalone output already carries everything else needed, nothing to copy here.
COPY --from=build --chown=yaadhum:yaadhum /srv/.next/standalone ./
COPY --from=build --chown=yaadhum:yaadhum /srv/.next/static ./.next/static
USER yaadhum

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
