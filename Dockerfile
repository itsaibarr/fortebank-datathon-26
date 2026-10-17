FROM vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.runtime.txt /app/
RUN python3 -m venv --system-site-packages /opt/forte-app
ENV PATH="/opt/forte-app/bin:$PATH"
RUN python -m pip install --no-cache-dir -r requirements.runtime.txt
COPY pyproject.toml README.md /app/
COPY contracts /app/contracts
COPY configs /app/configs
COPY src /app/src
RUN python -m pip install --no-cache-dir --no-deps .
COPY legal /legal
COPY web/out /app/web
ENV FORTE_FRONTEND_ROOT=/app/web
COPY scripts/container-entrypoint.sh /app/
COPY scripts/check_frozen_visual.py /app/
ENTRYPOINT ["bash", "/app/container-entrypoint.sh"]
