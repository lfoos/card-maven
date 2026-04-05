# Card Scan: Auto-populate Add Card from Photos

**Date:** 2026-04-05
**Status:** Approved

## Summary

When a user opens the "Add Card" modal, they can optionally upload front and/or back photos of a card and click "Scan Card" to auto-populate the form fields using Claude's vision API. Only empty fields are filled; anything the user has already typed is preserved.

## Architecture

### New backend endpoint: `POST /api/scan-card`

- Accepts a multipart form with optional `front` and `back` image files (same format as `POST /api/cards/:id/photos`)
- Reads `anthropic_api_key` from `config.json` (same pattern as `ebay_app_id`)
- Encodes images as base64 and sends them to Claude (claude-haiku-4-5 for cost efficiency) with a structured prompt
- Prompt asks Claude to extract the following fields and return them as a JSON object, using `null` for anything it cannot determine:
  - `player`, `year`, `card_set`, `variation`, `serial_number`, `grade`, `grader`, `condition_raw`
- Returns the JSON directly to the frontend — no database writes
- If `anthropic_api_key` is not configured, returns HTTP 400 with `{"error": "anthropic_api_key not configured"}`
- Image bytes are discarded after the API call; the scan endpoint does not persist photos

### Config

`config.json` gains a new optional key:

```json
{
  "ebay_app_id": "...",
  "anthropic_api_key": "sk-ant-..."
}
```

### Dependency

Add `anthropic` to `requirements.txt`.

## Frontend Changes

### 1. Photo slots visible in Add Card mode

The `photo-upload-section` div is currently hidden when opening the Add Card modal (`openAddCardModal()` sets `display:none`). Change it to always be visible — the same front/back upload slots that appear in edit mode will now appear at the top of the Add Card form.

### 2. Scan Card button

Add a "Scan Card" button below the photo slots. Behavior:
- Disabled until at least one photo file is selected
- On click: button enters loading state ("Scanning…"), calls `POST /api/scan-card` with the selected files via `FormData`
- On success: fills any **empty** form fields with returned values; leaves non-empty fields untouched; shows toast "Scan complete — fill in any remaining fields manually."
- On API error (including missing key): shows toast with the error message; form is unchanged

### 3. No other changes

All existing form fields, Save/Cancel buttons, edit-mode photo upload, and the save flow are unchanged. Scanning is purely additive.

## User Flow

1. User clicks **+ Add Card**
2. Photo upload slots are visible at the top of the modal
3. User uploads front and/or back photo
4. **Scan Card** button becomes active
5. User clicks **Scan Card** → fields populate (empty fields only)
6. User reviews, edits anything needed
7. User clicks **Save Card** → card is created, photos are uploaded (existing flow)

## Error Handling

| Situation | Behavior |
|---|---|
| No API key in config | Backend returns 400; frontend shows toast with setup instructions |
| Claude returns nulls (unreadable photo) | Empty fields stay empty; toast: "Scan complete — fill in any remaining fields manually." |
| Network or Claude API error | Toast with error message; form unchanged |
| User has already typed in a field | Scanned value for that field is ignored |

## Out of Scope

- Scanning from the card detail or edit views
- Confidence indicators or per-field highlighting
- Caching scan results
- Auto-triggering scan on photo upload (scan is always user-initiated)
