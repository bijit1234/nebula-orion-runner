# ─── Multi-stage build ────────────────────────────────────────────
# Stage 1: Build the React app
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm ci --silent

# Build args so the API URL is baked in at build time
ARG REACT_APP_API_URL=http://localhost:8000
ENV REACT_APP_API_URL=$REACT_APP_API_URL

# Copy source and build
COPY . .
RUN npm run build

# ─── Stage 2: Serve with nginx ─────────────────────────────────────
FROM nginx:alpine

# Copy the built app
COPY --from=builder /app/build /usr/share/nginx/html

# Copy our custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
