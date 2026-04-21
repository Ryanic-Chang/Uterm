FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md README_EN.md LICENSE CHANGELOG.md /app/
COPY src /app/src

RUN pip install --no-cache-dir -e ".[api]"

EXPOSE 9527/udp
EXPOSE 8080

CMD ["uterm-server", "--host", "0.0.0.0", "--port", "9527"]
