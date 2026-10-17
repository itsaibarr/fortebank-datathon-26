FROM vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.runtime.txt /app/
RUN python3 -m pip install --no-cache-dir -r requirements.runtime.txt
COPY pyproject.toml README.md /app/
COPY contracts /app/contracts
COPY src /app/src
COPY configs/person-tracking.json /app/configs/person-tracking.json
RUN python3 -m pip install --no-cache-dir --no-deps .
COPY scripts/container-entrypoint.sh /app/
ENTRYPOINT ["bash", "/app/container-entrypoint.sh"]
