# Use slim Node image
FROM node:20-alpine

# Create app directory, run as non-root
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy deps first (layer cache)
COPY package.json ./
RUN npm install --omit=dev

# Copy source
COPY server.js ./
COPY public/ ./public/

# Own files by non-root user
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 3000
CMD ["node", "server.js"]
