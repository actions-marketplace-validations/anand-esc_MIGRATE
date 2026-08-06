# harness/Dockerfile.py3
# Sandbox for running the CONVERTED code.

FROM python:3.12-slim

WORKDIR /app

# Harness is identical in both containers
COPY harness/harness.py /app/harness.py

# The converted source tree (swap this COPY line to point at the real output)
COPY converted/ /app/converted/

ENTRYPOINT ["python", "harness.py"]
