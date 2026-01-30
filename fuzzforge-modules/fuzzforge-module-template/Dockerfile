FROM localhost/fuzzforge-modules-sdk:0.0.1

COPY ./src /app/src
COPY ./pyproject.toml /app/pyproject.toml

# Remove workspace reference since we're using wheels
RUN sed -i '/\[tool\.uv\.sources\]/,/^$/d' /app/pyproject.toml

RUN uv sync --find-links /wheels
