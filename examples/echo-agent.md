```
```bash
curl -X POST http://localhost:<port>/api/v1/builds/upload \
  -F "file=@examples/echo-agent.tar.gz" \
  -F 'runtime={"type":"raw","dockerfile":""}' \
  -F "image_ref=registry.agent-system.svc.cluster.local:5000/echo-agent:0.1.0"
```
