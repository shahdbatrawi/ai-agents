# Required live demo

State your full name and say: "I will now demonstrate the functional requirements
for CSE 491 Homework 1". Announce each requirement. Keep console and browser visible
for requirements 1–3, with clear audio and video.

1. **Read:** Ask "How long did they work at University College of Applied
   Sciences?" Show the plan, SELECT, and accurate answer against the resume dates.
2. **Write:** Ask "Add TensorFlow as a skill to 3D Procedural Modeling with
   Blender API." Show generated Python, immediate badge update, and persistence
   after manual reload. Repeat and show the duplicate outcome.
3. **Coordination:** Ask "Does he know Rust? If not, add it to AI Agents & Prompt
   Engineering." Show the Read → Write plan and both actual executions in order.
   Repeat to show no second insertion.
4. **Schema:** From `homework 1` in another terminal, run:

   ```sh
   python -c "from flask_app.utils.database import database; print(database().query('SELECT role_id, role, domain FROM llm_roles'))"
   ```

   Show all four rows, the schema, and CSV prompt configurations.
5. **Concepts:** Open `prompt_engineering.md`, perform the three live comparisons,
   record actual observations, and explain the techniques and effectiveness.
6. **Content:** Ask "What is this page about?" Show the grounded Content Expert
   response. This expert generates no SQL; loading its role and resume context
   still reads server-side database data.

Submit your recording and the `Jamal_HM1` branch URL through the course form in
`rubric.md`. Automated tests do not replace the required video.
