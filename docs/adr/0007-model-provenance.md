# 0007. Record model provenance on every inference

**Status:** Accepted · **Date:** 2026-10-26

## Context
Identification (Phase 3) and grade estimation (Phase 4) use LLM vision models that will change over time. We need to measure accuracy per model and reprocess old results with new models.

## Decision
- **Every identification and grade estimate stores `model_provider`, `model_type`, and `prompt_version`.**
- **The model sits behind a `VisionModel` port.** The Anthropic API is the first adapter.
- **User confirmations are stored alongside predictions**, so they act as labeled data.

## Consequences
- Accuracy can be compared across models and prompts.
- A reprocess command can target "all results from model X".
- Rows are slightly larger.

## Alternatives considered
- **Logging provenance only:** not queryable, so it can't drive reprocessing.
