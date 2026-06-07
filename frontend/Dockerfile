# Stage 1: Build the Next.js application
# Use a Node.js LTS image with Alpine for a smaller base size.
FROM node:20-alpine AS builder

# Set the working directory inside the container
WORKDIR /app

# Copy package.json and package-lock.json to leverage Docker layer caching
# This step ensures that dependencies are re-installed only if package.json or package-lock.json changes.
COPY package.json package-lock.json ./

# Install project dependencies.
# `npm ci` is preferred in CI/CD environments for consistent builds based on package-lock.json.
# `--prefer-offline` uses cached packages if available.
# `--no-audit` skips security audit to speed up installation.
# `--omit=dev` prevents installation of devDependencies, reducing image size.
RUN npm ci --prefer-offline --no-audit --omit=dev

# Copy the rest of the application source code
COPY . .

# Build the Next.js application for production.
# NEXT_TELEMETRY_DISABLED=1 disables Next.js telemetry during the build.
# For optimal Docker builds with Next.js, it's highly recommended to configure
# `output: 'standalone'` in your `next.config.js`. This creates a minimal
# standalone server that includes only necessary files, making the final image smaller.
# If `output: 'standalone'` is NOT used, you would need to manually copy `node_modules`
# and the entire `.next` directory (excluding `cache`) in the next stage.
RUN NEXT_TELEMETRY_DISABLED=1 npm run build

# Stage 2: Create a smaller, production-ready image to run the application
FROM node:20-alpine AS runner

# Set the working directory inside the container
WORKDIR /app

# Copy the standalone output, public assets, and static files from the builder stage.
# These paths are typical when `output: 'standalone'` is configured in next.config.js.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/static ./.next/static

# Expose the port on which the Next.js application will run (default is 3000)
EXPOSE 3000

# Define the command to start the Next.js application.
# This assumes your `package.json` has a "start" script that runs `next start`.
CMD ["npm", "start"]