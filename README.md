<h1 align="center">Math Video Agent</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=flat&logo=python" />
  <img src="https://img.shields.io/badge/TypeScript-5-blue?style=flat&logo=typescript" />
  <img src="https://img.shields.io/badge/Next.js-16-black?style=flat&logo=next.js" />
  <img src="https://img.shields.io/badge/FastAPI-teal?style=flat&logo=fastapi" />
  <img src="https://img.shields.io/badge/LangGraph-orange?style=flat" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

**An AI agent that turns a math problem into an animated explanation video.**

A user types a math problem in plain English. The agent solves it with sympy, plans it into scenes, generates a Manim animation for each one, narrates it with TTS, and assembles everything into one MP4. The whole pipeline is orchestrated with LangGraph and runs in a sandboxed Docker container per job, with a Next.js frontend and a FastAPI backend on top.

---

## Features

- Solves algebra, geometry, trigonometry, calculus, linear algebra, and probability problems
- Verifies every answer with sympy instead of trusting the LLM's arithmetic
- Breaks the solution into scenes and generates Manim animation code for each one
- Adds spoken narration per scene with local TTS, timed to match each animation
- Retries failed renders with LLM-corrected code, falling back to a simplified scene if it still fails
- Streams live progress to the frontend over a WebSocket while a video is generated
- Keeps job history in the browser's local storage, with jobs resumable after a page reload
- Falls back to disk-stored job state if the API restarts mid-run

---

## System Architecture

Each job runs the pipeline below inside its own Docker container, orchestrated by a FastAPI job queue.

```mermaid
flowchart LR
    A[classifier] --> B[solver]
    B --> C[scene_planner]
    C --> D[tts]
    D --> E[codegen]
    E --> F[executor]
    F --> G[assembler]
```

### Workflow Pipeline

1. **classifier**

   - Identifies topic and difficulty with a cheap Gemini model, and cleans up the problem statement.

2. **solver**

   - Has an LLM extract the problem into a sympy code snippet, then actually runs sympy to get the real answer.
   - Has an LLM write a step-by-step explanation guided by that real result, so narration never contradicts the math.
   - Ends the run with a clear error if sympy genuinely cannot solve the problem, instead of letting the LLM guess.

3. **scene_planner**

   - Groups the solution's steps into scenes, not necessarily one-to-one, and writes each scene's narration and animation plan.

4. **tts**

   - Generates narration audio for every scene and measures its actual duration.
   - Runs before codegen, so animation timing can be built around real narration length.

5. **codegen**

   - Generates Manim animation code per scene, and stretches each scene's pauses to match its narration's measured duration.

6. **executor**

   - Renders each scene with Manim, retrying with LLM-corrected code up to three times on failure.
   - Falls back to a title-only scene if every attempt still fails, keeping scene count aligned with the audio.

7. **assembler**

   - Adds narration to each scene's video, then concatenates every scene into the final MP4.

---

## Technical Highlights

- **Per-node error handling**: every node owns its own failure path instead of a shared corrector or fallback node. `executor_node` retries a scene's Manim code with an LLM-corrected version up to 3 times, then falls back to a title-only scene so scene count always stays aligned with the narration. `solver_node` ends the run with a clear message when sympy genuinely cannot solve the problem, rather than letting the LLM invent an answer.
- **Narration drives scene timing, not the reverse**: TTS runs before code generation, so generated Manim code can stretch its pauses to match the narration's actual measured length. Animations are never shortened to fit; a scene simply runs a little past its narration, and the assembler pads the audio to match.
- **Sandboxed, restartable jobs**: each submitted job runs the full pipeline inside its own throwaway Docker container, talking to the host Docker daemon over the mounted socket. Output is written to disk keyed by a hash of the problem, so a job's status can still be served correctly even after the API restarts and loses its in-memory job state.
- **Faststart video assembly**: the final ffmpeg concat pass keeps `+faststart`, moving the file's index to the front. Without it, ffprobe and desktop players still find the audio track, but a browser starts decoding before it reaches the index and plays the video silently.
- **Constrained structured output**: classification and scene-type fields use `Literal` types with Gemini's schema-constrained generation, so the API is structurally unable to return a value like `"Algebra"` or a translated string outside the allowed set.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Pipeline orchestration | LangGraph |
| LLM | Gemini API (google-genai) |
| Math | sympy |
| Animation | Manim |
| Narration | Kokoro TTS |
| Video assembly | ffmpeg |
| Backend API | FastAPI |
| Frontend | Next.js, TypeScript, Tailwind CSS, Framer Motion |
| Sandboxing | Docker (per-job container) |
| Testing | pytest, Vitest, React Testing Library |

---

## Project Structure

```
math-video-agent/
├── backend/
│   ├── .env.example       # Template for backend/.env
│   ├── api/              # FastAPI app, job queue, sandbox orchestration
│   ├── config/            # Settings, LLM/TTS abstractions, structured-output schemas
│   ├── graph/              # LangGraph pipeline assembly, state, media paths
│   ├── nodes/              # One file per pipeline node
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/            # Next.js app router
│       ├── components/      # Chat UI, sidebar, job progress, video player
│       └── hooks/           # Job submission, WebSocket, local history
├── docker-compose.yml
└── justfile
```

---

## Quick Start

Requires Docker and Docker Compose.

```bash
git clone https://github.com/<user>/math-video-agent.git
cd math-video-agent
just up
```

The frontend is then available at `http://localhost:3000`, the API at `http://localhost:8000`.

Common `just` recipes:

```bash
just backend-install      # set up backend/.venv with runtime + dev deps
just backend-dev           # run the API locally with auto-reload
just backend-test          # run backend tests
just backend-check         # lint + format-check + type-check the backend

just frontend-install      # install frontend dependencies
just frontend-dev           # run the frontend dev server
just frontend-test          # run frontend tests
just frontend-check          # type-check + lint the frontend

just test                  # run backend + frontend test suites
just check                  # run backend + frontend lint/type checks

just up                    # build and start the full stack via Docker Compose
just down                  # stop and remove the stack
just logs                   # tail logs from the running stack
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in your key:

```env
GEMINI_API_KEY=your_key_here
```

---

## License

This project is licensed under the MIT License.
