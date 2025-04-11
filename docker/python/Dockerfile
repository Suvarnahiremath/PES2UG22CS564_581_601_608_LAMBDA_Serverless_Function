FROM python:3.9-slim

WORKDIR /app
COPY function.py /app/
COPY wrapper.py /app/

RUN pip install --no-cache-dir psutil

CMD ["python", "wrapper.py"]
