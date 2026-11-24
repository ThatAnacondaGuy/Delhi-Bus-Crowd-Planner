---
title: Delhi Bus Crowding Planner
emoji: 🚌
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: Plan a Delhi bus trip and see how crowded each stretch is
---

# Delhi bus crowding planner

Pick where you are going and when, and the planner shows the bus options with how crowded each stretch is likely to
be: seats free, standing, or crowded, with the evidence behind each estimate. A second screen, `/operator`, ranks the
extra trips that would take the most crowding off the network, and shows the corridors that need them.

The API is documented at `/docs`; `/v1/health` reports the data version and what is loaded.

This Space serves aggregate outputs only: crowding by route, stretch, corridor and scheduled trip, and the planner
tables. It contains no ticket-level or vehicle-level data.

Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.
