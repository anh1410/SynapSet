# Builds the React app, then serves it and the API from one FastAPI process (port 7860).
FROM node:22-slim AS web
WORKDIR /w
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json postcss.config.js tailwind.config.js ./
COPY src src
RUN npm run build

FROM python:3.13-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
# CPU-only PyTorch keeps the image small; sentence-transformers then finds it already installed.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/app/.cache ENVIRONMENT=production DISABLE_CODE_EXECUTION=true
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
COPY app app
COPY --from=web /w/dist dist
RUN mkdir -p data && chown -R user:user /app
USER user
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
