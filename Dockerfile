FROM ghcr.io/astral-sh/uv:0.13.6-python3.15-trixie-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .
RUN uv run blog.py build --clean

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
