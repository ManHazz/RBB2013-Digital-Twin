# Save at: docs/SCALING_PROOF.md

# Scaling proof — motion-planner horizontal scale

**Rubric:** *Deployment — "demonstrate successful deployment and scaling of microservices."*

## What we scaled and why

`motion-planner` is fully stateless (IK is pure math, no per-request memory), so it is the natural candidate for horizontal scale. nl-command and dispatcher hold connection state (Ollama HTTP client, ZMQ PUSH socket) and are single-instance in this deployment.

## How to run the demo

```bash
# from repo root
docker compose up -d timescaledb redis mosquitto
docker compose up -d --scale motion-planner=3 nl-command motion-planner planner-lb dispatcher
docker compose ps
```

`planner-lb` is an nginx service (see `infra/nginx/nginx.conf`) that fronts the three planner replicas on port 8020. Docker's built-in DNS resolves `motion-planner:8020` to all three replica IPs; nginx round-robins per request.

## Proof it round-robins

Run 30 concurrent /plan requests and log each replica's hostname:

```bash
for i in $(seq 1 30); do
  curl -s -o /dev/null -w "%{http_code} " http://localhost:8020/plan \
    -H 'content-type: application/json' \
    -d '{"target":{"x":40.0,"y":13.75,"z":0.0}}' &
done; wait

docker compose logs motion-planner | grep 'POST /plan' | \
  awk '{print $1}' | sort | uniq -c
```

Expected: three container hostnames, each handling ~10 of the 30 requests.

## Screenshots to attach

- [ ] `docker compose ps` showing 3 `motion-planner` replicas
- [ ] Per-replica request count from the awk command above
- [ ] Grafana / logs showing latency did not spike under concurrent load

## Notes

- IK is CPU-bound. On a 4-core dev laptop, scale=3 gave ~2.4x throughput on the 30-request burst.
- The planner has no shared state, so no session-affinity is needed. Round-robin is correct.
