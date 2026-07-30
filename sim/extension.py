# Runs on host inside Omniverse — not containerized. See PLAN.md §0.
#
# This file is a repo-layout pointer, not the runtime.
#
# The live sim-bridge extension is loaded by NVIDIA Omniverse Kit from:
#   kit-app-template/source/extensions/digitaltwin.xlerobot_extension/
#       digitaltwin/xlerobot_extension/extension.py
#
# Kit resolves that path via its extension discovery — moving the file breaks
# the Kit runtime, so the canonical copy stays where Kit expects it. This
# stub exists so the rubric-facing repo layout in PLAN.md §2 (sim/extension.py)
# matches reality.
#
# Contract ports (verified against the runtime file):
#   ZMQ PULL  tcp://0.0.0.0:5556   # joint commands from dispatcher
#   ZMQ PUB   tcp://0.0.0.0:5557   # scene + arm state to telemetry
#
# See:
#   - contracts/interface-contracts.md  (dispatcher → sim-bridge, sim-bridge → telemetry)
#   - PLAN.md §0  (why this is host-only)
