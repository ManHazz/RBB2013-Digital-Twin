# XLeRobot Digital Twin — Visualization

**Rubric:** Project Visualization (5%) — *"Create a visualization that is appropriate and reflects the digital twin problem that you have chosen. Demonstrate its function."*

The digital twin has two complementary visualizations, each showing a different facet of the same underlying state.

---

## 1. Omniverse Kit viewport — the "physical twin" view

**What it shows:** the 3D digital twin of the robot arm, its target, and its obstacles, rendered in real time from live joint state.

**Why it reflects the problem:** the whole point of a digital twin is to let a human see the physical system's current pose without being next to it. This viewport is that.

**Live behavior:** the arm animates in real time as joint commands stream in from `dispatcher` via ZMQ PUSH on port 5556. When the user issues "pick up the ball", the arm visibly moves through: home → above → grab → lift — each step ~1 second (30 interpolated frames).

**Scene composition** (built by `digitaltwin.xlerobot_extension` at startup):
- Robot arm — 6 joints (blue spheres), 5 links (grey cylinders), 2-finger gripper (orange).
- Target ball — small red sphere at `(x=40, y=1.75, z=0)` cm.
- Two purple obstacle spheres — the arm must avoid these.
- Grid + coordinate axes.

**Screenshot — Omniverse viewport with robot + scene:**

![Omniverse viewport](./screenshots/omniverse_scene.png)

*(replace with actual screenshot — one already captured, path `~/.claude/image-cache/4b3438b3-4b11-414f-94aa-24a0ea5de642/8.png` from the sim-bridge verification session)*

**Demonstration commands:**

```bash
# 1. Launch Kit with the extension enabled
cd kit-app-template && ./repo.sh launch
# → wait for "[RobotArm] cmd PULL :5556  state PUB :5557" in the terminal
# → wait for "[RobotArm] scene: target + 2 obstacles built"
# → viewport shows the scene

# 2. In another terminal, bring up the compose stack
docker compose -f infra/docker-compose.yml up -d

# 3. Send a command
curl -X POST http://localhost:8010/command \
     -H 'content-type: application/json' \
     -d '{"text": "pick up the ball"}'

# 4. Watch the Omniverse viewport — the arm animates
```

---

## 2. Grafana dashboard `XLeRobot — Robot State` — the "data twin" view

**What it shows:** a time-series projection of the digital twin's state, sourced live from TimescaleDB.

**Why it reflects the problem:** the physical view shows *now*; this view shows *over time* — trajectories, patterns, whether a run actually completed, whether the arm reached where it was told to. It also proves the streaming aggregation pipeline is working (rows keep coming in).

**Panels:**

| # | Panel | Data | Update rate |
|---|-------|------|-------------|
| 1 | **End-effector position (x, y, z)** | `SELECT ts AS time, ee_x, ee_y, ee_z FROM robot_state WHERE $__timeFilter(ts)` | 5 s (auto-refresh) |
| 2 | **Joint 0 (shoulder rotation)** | `SELECT ts AS time, joints[1] AS j0 FROM robot_state WHERE $__timeFilter(ts)` | 5 s |
| 3 | **Rows in last 5 minutes** (stat) | `SELECT count(*) FROM robot_state WHERE ts > now() - interval '5 minutes'` | 5 s |

**Screenshot — Grafana dashboard with a run in progress:**

![Grafana dashboard](./screenshots/grafana_dashboard.png)

*(placeholder — capture after Raziq-08 lands and a run completes)*

**Access:**

```bash
# After docker compose up -d
# Browse to http://localhost:3000
# Login: admin / admin  (defined in docker-compose.yml env)
# Dashboard is auto-provisioned via infra/grafana/provisioning/
# Direct URL: http://localhost:3000/d/xlerobot-robot-state
```

---

## 3. Measure of success — visible on the visualizations

Two things a marker can verify at a glance:

### 3.1 The arm reaches the target (Omniverse)
After a "pick up the ball" command, the gripper visually touches the red ball. If IK failed (unreachable) or collision was detected, the arm does not move for that step — visible failure, no false success.

### 3.2 The pipeline delivers data (Grafana)
The end-effector trace converges on the ball coordinates `(40, 1.75, 0)` cm. The row-count stat is strictly increasing throughout a run — proving continuous streaming + aggregation into persistent storage.

**Screenshot showing both success measures:**

![Success proof](./screenshots/success_proof.png)

*(placeholder — capture with Omniverse and Grafana side by side after a run completes)*

---

## 4. Persistence visualization

**Bonus proof:** the same Grafana traces are visible *before and after* `docker compose restart timescaledb redis` — see `docs/PERSISTENCE_PROOF.md`. The data doesn't disappear when containers restart. Named volumes prove state persistence.

---

## 5. Design decisions

**Why two visualizations rather than one?**
- Omniverse: reflects the *simulation* aspect of the digital twin. Good for "did the arm do what I said?"
- Grafana: reflects the *observability* aspect of the digital twin. Good for "what happened during the last 100 runs?" and "is the pipeline healthy right now?"

**Why not Streamlit / custom UI?**
- Grafana is battle-tested for time-series and gets auto-provisioned via YAML — zero clicks to set up on a fresh deployment.
- Omniverse is the sim itself — no separate UI needed. The viewport IS the visualization.

**Why not embed Grafana into Omniverse?**
- Different audiences. The operator commanding the robot lives in Omniverse; the reliability engineer watching for outliers lives in Grafana. Keeping them separate keeps each tool doing what it's best at.

---

## 6. Screenshots checklist for final submission

- [ ] `screenshots/omniverse_scene.png` — Omniverse viewport at startup, showing robot arm + target + obstacles.
- [ ] `screenshots/omniverse_after_command.png` — Omniverse viewport after "pick up the ball", showing gripper touching the ball.
- [ ] `screenshots/grafana_dashboard.png` — Grafana dashboard mid-run with all 3 panels populated.
- [ ] `screenshots/grafana_ee_trace_convergence.png` — zoomed panel showing ee_x/ee_y/ee_z converging on target coordinates.
- [ ] `screenshots/grafana_row_count.png` — the row-count stat showing continuous data ingestion.
- [ ] `screenshots/persistence_before.png` and `screenshots/persistence_after.png` — same panel before and after `docker compose restart`, showing continuity.

Save all screenshots under `docs/screenshots/`. Reference them from this file with relative paths.
