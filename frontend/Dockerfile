# --- Build Stage ---
FROM oven/bun:1-alpine AS build

WORKDIR /app

# Copy package configurations first for Bun caching
COPY frontend/package.json ./
RUN bun install

# Copy application files
COPY frontend/ ./

# Compile production bundles using Bun
RUN bun run build

# --- Serve Stage ---
FROM nginx:1.25-alpine

# Copy custom Nginx routing configuration
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
