# XLeRobot Digital Twin — Live Demo Script

**Purpose:** exact commands to type + expected outputs, so the live demonstration to the marker cannot go wrong. Also serves as a manual smoke test.

**Time budget:** ~10 minutes total.

---

## Pre-flight (do 30 min before the demo)

Verify each item. If any is red, fix before the demo starts.

- [ ] Docker Desktop is running (`docker ps` returns without error).
- [ ] Ollama is running on host with the model pulled:
  ```bash
  ollama list | grep qwen2.5:3b   # must print a line
  # if not, run: ollama pull qwen2.5:3b && ollama serve
  ```
- [ ] Free disk (≥5 GB) for the container images and volumes:
  ```bash
  df -h /var/lib/docker
  ```
- [ ] Git repo on `main` at the sprint-2 tag:
  ```bash
  cd path/to/RBB2013-Digital-Twin
  git checkout main && git pull
  git tag -l   # must include sprint-1 and sprint-2
  ```
- [ ] All services built cleanly:
  ```bash
  docker compose -f infra/docker-compose.yml build   # ~1 min if cached
  ```

---

## Demo — beat by beat

### Act 1: Bring up the stack (2 min)

```bash
cd path/to/RBB2013-Digital-Twin

# Start the compose stack
docker compose -f infra/docker-compose.yml up -d

# Show what came up
docker compose -f infra/docker-compose.yml ps
```

**Say aloud:** "Every microservice runs in its own container. Timescale, Redis, Mosquitto, and Grafana are the infra tier. The five app services — nl-command, motion-planner behind nginx, dispatcher, actuation, telemetry — are our code."

**Then start Omniverse Kit** (in a new terminal, keep it visible):

```bash
cd kit-app-template
./repo.sh launch
```

Wait for these two lines in the log — this is the "sim-bridge is live" signal:

```
[RobotArm] cmd PULL :5556  state PUB :5557
[RobotArm] scene: target + 2 obstacles built
```

**Say aloud:** "sim-bridge lives on the host, not in a container — Omniverse needs GPU-accelerated Vulkan and the Kit runtime. It talks to the compose network over ZMQ via `host.docker.internal`."

Point at the Omniverse viewport: robot arm, red target ball, two purple obstacles.

### Act 2: Send a command (1 min)

```bash
curl -X POST http://localhost:8010/command \
     -H 'content-type: application/json' \
     -d '{"text": "pick up the ball"}' \
     | jq
```

**Expected output:**
```json
{
  "x": 40.0,
  "y": 13.75,
  "z": 0.0
}
```

**Say aloud:** "The LLM parsed the sentence, produced an action plan, and mapped the first action to a target pose 12 cm above the ball — the approach position."

**Point at the Omniverse viewport:** the arm animates through the interpolated frames toward the target.

### Act 3: Show live telemetry (1 min)

Open Grafana in a browser:

```
http://localhost:3000
```

Login `admin` / `admin`. Navigate to the dashboard **XLeRobot — Robot State** (already provisioned, no manual setup).

**Point at the panels:**
- **End-effector position (x, y, z)** — three traces, growing to the right as new data arrives.
- **Joint 0** — shoulder rotation over time.
- **Rows in last 5 minutes** — number climbing, proving the pipeline delivers data continuously.

**Say aloud:** "Telemetry subscribes to the sim's ZMQ PUB socket, decodes each state message, and dual-writes: one row per tick to TimescaleDB for history, plus the same message overwrites `state:latest` in Redis for O(1) latest-state reads."

### Act 4: Prove persistence (2 min)

**Data + state both survive container restart** — this is the "persistence in data AND state storage" rubric line.

```bash
# 1. Baseline reads
docker compose exec timescaledb psql -U postgres -d robot \
  -c "SELECT count(*) FROM robot_state;"
docker compose exec redis redis-cli GET state:latest | head -c 100
```

Note the row count and the JSON prefix.

```bash
# 2. Restart the persistence containers
docker compose restart timescaledb redis
sleep 5
```

```bash
# 3. Re-read — identical values prove persistence
docker compose exec timescaledb psql -U postgres -d robot \
  -c "SELECT count(*) FROM robot_state;"
docker compose exec redis redis-cli GET state:latest | head -c 100
```

**Say aloud:** "Row count is the same. Redis latest state is byte-identical. Named Docker volumes and Redis's AOF+RDB persistence keep both halves of the digital twin state across restarts. See `docs/PERSISTENCE_PROOF.md` for the full procedure with screenshots."

### Act 5: Prove horizontal scale (2 min)

```bash
# Scale motion-planner from 1 to 3 replicas
docker compose -f infra/docker-compose.yml up -d --scale motion-planner=3
docker compose ps motion-planner
```

**Show the 3 replicas listed.**

```bash
# Burst 30 concurrent plan requests through the nginx load balancer
for i in $(seq 1 30); do
  curl -s -o /dev/null -w "%{http_code} " http://localhost:8020/plan \
    -H 'content-type: application/json' \
    -d '{"target":{"x":40.0,"y":13.75,"z":0.0}}' &
done; wait; echo
```

**Show all 200s in the output.**

```bash
# Count requests per replica
docker compose logs --no-log-prefix motion-planner 2>&1 | \
  grep 'POST /plan' | awk '{print $1}' | sort | uniq -c
```

**Say aloud:** "Motion-planner is stateless — pure IK math per request — so it scales horizontally. nginx uses Docker's built-in DNS to round-robin across the three replicas. Each handled roughly a third of the burst. See `docs/SCALING_PROOF.md`."

### Act 6: Prove CI + regression (1 min)

Open the GitHub Actions tab:

```
https://github.com/ManHazz/RBB2013-Digital-Twin/actions
```

Point at the most recent workflow run.

**Say aloud:** "Every push runs lint → unit → integration (with real Timescale, Redis, Mosquitto service containers) → regression. Regression is a fixed set of golden IK targets — if the IK math drifts, CI turns red. This is the automatic build + automatic regression test loop the rubric asks for. See `.github/workflows/ci.yml`."

### Act 7: Show sprint version-control evidence (1 min)

```bash
# Sprint tags
git tag -l
# → sprint-1
# → sprint-2

# The merge commits
git log --merges --oneline main | head -10
```

**Say aloud:** "Two sprint cycles, tagged. Each sprint ends with a single integration PR merged into main — preserving every teammate's authored commits as evidence of individual + group work across all modules. See `docs/SPRINT_LOG.md` for the sprint-by-sprint deliverables."

### Act 8: Wrap up (30 s)

Point at the file tree:

```
docs/
├── SPECIFICATION.ipynb   ← problem, purpose, state, streams, viz
├── ARCHITECTURE.md       ← component diagram + service catalog
├── AI_MODEL.md           ← LLM + IK models, ingested data, updates state
├── DATA_STREAMING.md     ← state definition, streams, aggregation
├── VISUALIZATION.md      ← both views, measure of success
├── SCALING_PROOF.md      ← Ariq's scale demo
├── PERSISTENCE_PROOF.md  ← Raziq's restart demo
├── SPRINT_LOG.md         ← per-sprint deliverables
└── DEMO.md               ← this file
```

**Close:** "That's the digital twin — natural language in, validated collision-free motion in simulation, actuation to the physical robot over MQTT, streaming telemetry into a persistent data store, live observability in Grafana. Every microservice is defined, contracted, containerized, tested at three tiers, and deployed via one command."

---

## Troubleshooting during the demo

| Symptom | Likely cause | 30-second fix |
|---------|--------------|--------------|
| `POST /command` returns 502 | Ollama not running | `ollama serve &` in a spare terminal |
| Arm doesn't move in Omniverse | sim-bridge crashed or ports not bound | Check Kit terminal for red errors; restart with `./repo.sh launch` |
| Grafana dashboard empty | telemetry not receiving state | Check `docker compose logs telemetry` — should see a message every 100 ms |
| Timescale row count doesn't grow | Same as above | Same check |
| `docker compose up` fails | Docker Desktop paused | Resume Docker Desktop, retry |
| Compose says "port already in use" | A previous run didn't clean up | `docker compose -f infra/docker-compose.yml down` then retry |

If anything unrecoverable happens on stage: fall back to walking through the screenshots in `docs/VISUALIZATION.md` and `docs/PERSISTENCE_PROOF.md`, and the diff in the PR that merged sprint 2. The proof is committed, whether the live demo cooperates or not.
