# 0002. Ports and adapters for external dependencies

**Status:** Accepted · **Date:** 2026-10-26

## Context
Several dependencies are expected to change: the market data source (fixtures today; eBay or a paid provider later), the vision model (Anthropic now, maybe Bedrock or others later), embeddings, the reference catalog, object storage, and the message bus.

## Decision
- **Domain code depends on small `Protocol` ports.** Today that is `EventPublisher`; `MarketDataSource`, `VisionModel`, `ImageEmbedder`, `ReferenceCatalog`, and `ObjectStore` follow as their features arrive.
- **Concrete adapters live at the edges.** Each port ships with an in-memory or fixture adapter used in tests and local development.

## Consequences
- Swapping a provider means writing a new adapter and its contract test.
- Tests are fast and deterministic.
- Cost: a thin indirection layer, kept honest by adding a port only when a second implementation (even a fake) exists.

## Alternatives considered
- **Calling SDKs directly from services:** simpler at first, but every provider change touches business logic.
