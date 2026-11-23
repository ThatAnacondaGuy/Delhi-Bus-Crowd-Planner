---
title: Delhi Bus Crowding Planner
emoji: 🚌
colorFrom: green
colorTo: yellow
sdk: static
app_file: index.html
pinned: false
short_description: Plan a Delhi bus trip and see how crowded each stretch is
---

# Delhi bus crowding planner: live demo

This is a ready-made demo of a Delhi bus journey planner that shows how crowded each stretch of a bus ride usually is:
seats free, standing, or crowded, with the evidence behind each estimate.

It is a static page. Pick a place to start from, a place to go to and one of the departure times, and it shows the
answer the planner computed ahead of time. The answers come from the same model as the full planner, which can plan
any trip between any two places at any time but needs to run from the code. The full planner, the API and the data
pipeline are on GitHub: https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner

A second screen, `operator.html`, ranks the extra bus trips that would take the most people out of crowded buses and
shows the corridors that need them. It reads the same ready-made files.

Counts are scaled up from app tickets. Women riding free and pass holders are not in this data, so buses can be fuller
than shown. This Space holds aggregate outputs only: crowding by route, stretch, corridor and scheduled trip. It
contains no ticket-level or vehicle-level data.

Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.
