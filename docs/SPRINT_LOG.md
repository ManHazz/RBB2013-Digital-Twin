# Sprint Log — XLeRobot Digital Twin

## Sprint 1 (26 Jul – 30 Jul 2026)

**Goal:** Scaffold repo, freeze shared pydantic v2 contracts, extract each subsystem into its own FastAPI service, unit tests with pass AND fail cases.

**Deliverables that shipped:**

- Repo layout per PLAN.md §2 (Aiman-01)
- `services/shared/schemas.py` v1.0 — pydantic v2 contract types (Aiman-02)
- `contracts/interface-contracts.md` skeleton (Aiman-03)
- `sim/extension.py` pointer stub → real Kit runtime (Aiman-04)
- `nl-command` service + Ollama integration + happy + fail unit tests (Bento-01..04)
- `motion-planner` service wrapping robot_ik + IK round-trip / unreachable / colliding unit tests (Ariq-01..05)
- `dispatcher` service + 30 fps interpolator + ZMQ PUSH + unit tests (Ibrohim-01..03)
- `actuation` service — refactored mid-sprint to HTTP-triggered MQTT publisher (Ibrohim-04, FIX-03)
- `telemetry` daemon + TimescaleDB init.sql + Timescale + Redis unit tests (Raziq-01..05)
- All 10 interface contract rows filled (Bento-05, Ariq-06, Ibrohim-06/FIX-06, Raziq-06)

**Mid-sprint integration fixes** (`FIXES_SPRINT1.md`):

- Ariq-FIX-01/02: motion-planner Dockerfile rebuild + BOM strip (applied by Aiman on Ariq's branch as commit `17edbc1`)
- Ibrohim-FIX-01..06: actuation Dockerfile, dispatcher ZMQ moved to startup handler, actuation rewritten as HTTP service on :8040 to remove port collision with sim-bridge, real MQTT test, integration branch merged in, contract rows filled

**Group merge:** all five feature branches merged into `feat/integration`, then PR #2 into `main`. Tag `sprint-1` pushed to origin.

---

## Sprint 2 (31 Jul 2026)

**Goal:** Wire compose, prove persistence, add CI + regression + integration + system tests, demonstrate horizontal scaling of the stateless planner, ship Grafana dashboard.

**Deliverables that shipped:**

- Aiman: `infra/docker-compose.yml` + mosquitto.conf (A-06), `tests/system/test_end_to_end.py` (A-07), 4 rubric-artifact notebooks (SPECIFICATION.ipynb, AI_MODEL.ipynb, DATA_STREAMING.ipynb, DEPLOYMENT.ipynb), VISUALIZATION.md, DEMO.md, ARCHITECTURE.md, DEV_PRACTICES.md
- Aiman-assists during smoke test: fix dispatcher Dockerfile (`ab24b6e`), enable Kit extension + pyzmq pipapi (`0dc0714`), full end-to-end integration hotfixes (`f5d2a04`), human-friendly Grafana panels (`d72d6e7`, `4f565db`, `35c3622`), CI lint autofix + ruff config (`14b8bc5`), CI httpx dep (`4a21be8`), skip test_sim_to_telemetry in CI (`ec93c23`), dispatcher LINGER=0 (`b831b5f`), telemetry auto-reconnect (`35c3622`), pitch-sign fix for arm-reach visual (`4f565db`), Pipeline health mapping (`7604c6b`, `0587b1d`)
- Bento: integration test nl→planner (Bento-06), CI pipeline lint/unit/integration/regression (Bento-07), golden IK regression suite (Bento-08)
- Ariq: integration test planner→dispatcher (Ariq-07), nginx round-robin + `docs/SCALING_PROOF.md` (Ariq-08)
- Ibrohim: integration test actuation→mosquitto with real broker via testcontainers (Ibrohim-07)
- Raziq: integration test sim→telemetry with real Timescale + Redis (Raziq-07), Grafana provisioning + `robot_state` dashboard (Raziq-08), persistence proof procedure (`docs/PERSISTENCE_PROOF.md`, Raziq-09)

**Integration bugs discovered + fixed during live smoke test:**

- Dispatcher `try/except` had broken indentation — file wouldn't import → rewrote cleanly.
- Dispatcher tried to `bind()` port 5556, colliding with sim-bridge which also binds it → changed to `connect()` via `SIM_BRIDGE_ADDR` env var.
- Ollama listened on 127.0.0.1 only → containers couldn't reach it → operator set `OLLAMA_HOST=0.0.0.0`.
- Host ports 5432 / 3000 already taken by other host services → compose switched to `expose:` internal-only; Grafana remapped to host `:3001`.
- Sim-bridge wire format didn't match the `SimState` contract → telemetry `_normalize_from_sim()` adapter converts.
- RUN_ME scripts had a `echo >>` bug that concatenated req lines → `requirements.txt` files fixed.
- Dispatcher sending list-format joints, sim expecting dict-format → extension.py accepts both.
- Kit rotation convention around +Z tilts arm opposite to robot_ik's +X → negated j1/j2/j3 in extension.py so visual matches IK.
- Telemetry's persistent Postgres connection died on `docker compose restart timescaledb` → auto-reconnect logic added.
- Dispatcher ZMQ shutdown hung in CI without a peer → `zmq.LINGER=0` added.
- Ruff lint hit 13 issues; 12 auto-fixed and 1 (RUF007 in robot_ik.py) ignored per `ruff.toml`.
- CI regression job missed `httpx` for FastAPI TestClient → added.
- CI integration hung on Timescale image pull → `test_sim_to_telemetry.py` skipped in CI (runs locally + covered by system test).

**Group merge:** sprint-2 code + all hotfixes merged into `main` via PR #2 (sprint-2 code) and PR #3 (post-smoke-test integration hotfixes). Tag `sprint-2` pushed to origin.

---

## Sprint boundary rules (enforced across both sprints)

- One task = one commit (see `TASK_ALLOCATION.md`).
- Feature branches never pushed to `main` directly — always via PR.
- `services/shared/schemas.py` is frozen at v1.0; only Aiman (tech lead) edits it.
- Sprint end = every teammate's contribution merged in one PR, then tag pushed.

---

## Version-control artifacts on GitHub

- Sprint tags: `sprint-1`, `sprint-2`
- Group merge PRs: #2 (sprint-1 + sprint-2 code), #3 (sprint-2 hotfixes)
- CI workflow: `.github/workflows/ci.yml`
- All 5 teammates authored commits on `main` (5-contributors indicator on merged PRs)
