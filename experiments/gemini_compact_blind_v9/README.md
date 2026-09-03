# Gemini Compact Blind V9

Three previously unseen deterministic automotive tasks for an unchanged compact
source-only prompt. Task IDs: 0 injector correction, 1 contactor diagnostic,
2 torque vectoring. Build with `./experiments/gemini_compact_blind_v9/build_s32k148.ps1`.

Board expressions: `g_star_blind_v9_complete`, `g_star_blind_v9_current`, and
`g_star_blind_v9_results` (expand `points[0..2]`). Do not add these measurements
to RAG until all Gemini predictions have been frozen.
