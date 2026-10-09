# syntax=docker/dockerfile:1
# The ExamLeaf admin console (admin.examleaf.in): Next.js standalone output on Node 24 LTS, run as the image's
# unprivileged "node" user, as the public site's image (../examleaf-frontend/Dockerfile). docker-compose.yml
# (examleaf-web/) builds it as the "admin" service. NEXT_PUBLIC_* values are compiled into the build, so they are build
# arguments, not runtime settings; none of them is a secret. The staff API mock is compiled out of every build.

FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_WEBSITE_URL
ARG NEXT_PUBLIC_ERP_URL=""
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_WEBSITE_URL=$NEXT_PUBLIC_WEBSITE_URL \
    NEXT_PUBLIC_ERP_URL=$NEXT_PUBLIC_ERP_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN test -n "$NEXT_PUBLIC_SITE_URL" || (echo "build with --build-arg NEXT_PUBLIC_SITE_URL=https://admin.examleaf.in" && exit 1)
RUN test -n "$NEXT_PUBLIC_WEBSITE_URL" || (echo "build with --build-arg NEXT_PUBLIC_WEBSITE_URL=https://examleaf.in" && exit 1)
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
# the process only (src/app/api/health/route.ts): a Django outage must not restart the console
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health/').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"
CMD ["node", "server.js"]
