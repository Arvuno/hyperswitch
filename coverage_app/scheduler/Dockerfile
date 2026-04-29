FROM python:3.11-slim

# Tools the pipeline needs: git for tag history, cron for scheduling, tzdata for IST.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git cron tzdata bash ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# openpyxl is needed by merge_prod_data.py / merge_cypress_coverage.py
RUN pip install --no-cache-dir openpyxl==3.1.5

# Cron entry: run pipeline at 10:00 IST every day.
COPY crontab /etc/cron.d/coverage
RUN chmod 0644 /etc/cron.d/coverage \
    && crontab /etc/cron.d/coverage \
    && touch /var/log/cron.log

COPY run_pipeline.sh /usr/local/bin/run_pipeline.sh
RUN chmod +x /usr/local/bin/run_pipeline.sh

ENV REPO_ROOT=/repo

# Foreground cron + tail logs so docker logs stays useful.
CMD bash -c "service cron start && tail -F /var/log/cron.log /repo/coverage_app/logs/*.log 2>/dev/null"
