FROM eclipse-temurin:21-jre-noble

# Install Python3, PyYAML, Git, Bash, Curl, and CA certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        git \
        bash \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure git default user identity
ARG GIT_USER_NAME="Hybrid Syncer"
ARG GIT_USER_EMAIL="syncer@example.com"
RUN git config --global user.name "$GIT_USER_NAME" && \
    git config --global user.email "$GIT_USER_EMAIL"

# Download patched Copybara JAR executable
RUN curl -fL -o /opt/copybara_deploy.jar "https://github.com/miv403/copybara-http/releases/download/v20260727-patch/copybara_deploy-PATCHED.jar"

# Create copybara launcher script in PATH
RUN echo '#!/bin/bash' > /usr/local/bin/copybara && \
    echo 'exec java -jar /opt/copybara_deploy.jar "$@"' >> /usr/local/bin/copybara && \
    chmod +x /usr/local/bin/copybara

WORKDIR /app

ENTRYPOINT ["python3", "/app/hybrid-syncer.py"]
