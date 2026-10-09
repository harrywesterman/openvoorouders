ARG NODE_BASE
FROM ${NODE_BASE}
LABEL org.opencontainers.image.source="https://github.com/harrywesterman/openvoorouders"
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 10001 agent
WORKDIR /opt/opencode
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && ln -s /opt/opencode/node_modules/.bin/opencode /usr/local/bin/opencode
COPY tools/ /opt/tools/
COPY uv-requirements.txt /opt/uv-requirements.txt
RUN python3 -m venv /opt/uv && /opt/uv/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes -r /opt/uv-requirements.txt \
 && /opt/uv/bin/uv sync --project /opt/tools/archiefakte --frozen --no-dev --python /usr/bin/python3 \
 && cd /opt/tools/delpher && npm ci && npm run build
COPY modules/api-mcp/bin/ /opt/tools/webtrees-bin/
COPY agent/ /opt/agent/
COPY release.json /opt/agent/release.json
COPY skills/ /opt/skills/
COPY tools/research-template/docs/werkwijze/ /opt/skills/nederlands-onderzoek/references/
RUN chmod -R a+rX /opt/tools /opt/skills /opt/agent && mkdir -p /workspace /opt/ovo-control
ENV PATH="/opt/uv/bin:${PATH}" HOME=/home/agent
USER 10001:10001
WORKDIR /workspace
CMD ["python3", "/opt/agent/server.py"]
