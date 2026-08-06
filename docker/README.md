# trigger server and automatic syncer

automatically syncs two gitea instance repos with webhooks and minimal http server.

```bash
docker compose up -d --build
docker compose logs -f syncer-runner
docker compose down
```
