# Learned skill aliases — autonomous curation log

## 2026-06-20 — human override

- REVERTED `claude code` -> `claude`: Claude Code (the agentic CLI) and Claude
  (the model) are distinct skills and should be taught separately. The judge's
  "code is implied" was wrong here. 4 of the run's 5 merges kept.

## 2026-06-20 — 5 new alias(es)

- MERGE `autonomous ai agents` + `autonomous agents` -> `autonomous ai agents` (cos 0.908) — same concept
- MERGE `postgres extension (paradedb)` + `postgres extension` -> `postgres extension` (cos 0.831) — paradedb is a specific extension
- MERGE `claude code` + `claude` -> `claude` (cos 0.8) — code is implied
- MERGE `tokio` + `rust/tokio` -> `tokio` (cos 0.725) — rust is implied
- MERGE `bpf` + `linux bpf` -> `bpf` (cos 0.667) — linux is implied
- keep `postgres extensions` / `postgres extension` separate (cos 0.8) — plural vs singular
- keep `webassembly` / `webassembly wheels` separate (cos 0.789) — wheels is a specific application
- keep `autonomous ai agents` / `ai agents` separate (cos 0.788) — autonomous is a specific type
- keep `temporal` / `temporal technologies` separate (cos 0.713) — technologies is a broader concept
- keep `clickhouse monitoring` / `clickhouse` separate (cos 0.707) — monitoring is a specific application
- keep `rust/tokio` / `rust` separate (cos 0.688) — tokio is a specific library
- keep `llm` / `llm apis` separate (cos 0.686) — apis is a specific application
- keep `agentic ai` / `ai agents` separate (cos 0.683) — agentic is a specific type
- keep `cube core` / `cube core semantic layer` separate (cos 0.682) — semantic layer is a specific component
- keep `inference stack` / `llm training and inference stack` separate (cos 0.673) — llm training is a specific application
- keep `postgres extension (paradedb)` / `postgres extensions` separate (cos 0.671) — paradedb is a specific extension
- keep `datalog` / `deconstructing datalog` separate (cos 0.653) — deconstructing is a specific analysis
- keep `llm` / `llm agents` separate (cos 0.649) — agents is a specific application
- keep `llm` / `llm gateway` separate (cos 0.632) — gateway is a specific application
- keep `llm training` / `llm training and inference stack` separate (cos 0.629) — inference stack is a specific application
- keep `azure ai foundry` / `foundry` separate (cos 0.622) — azure ai is a specific application
- keep `llm` / `llm training` separate (cos 0.617) — training is a specific application
- keep `llm agents` / `ai agents` separate (cos 0.616) — llm is a specific type
- keep `miri` / `ffi in miri` separate (cos 0.612) — ffi is a specific application
