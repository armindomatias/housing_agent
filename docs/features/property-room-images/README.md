# Feature: Property & Room Images in Analysis Results

**Branch:** `feat/vision-room-clustering`
**Status:** Completed
**Date:** 2026-02-18

## Goal

Surface the images that the backend already sends in the analysis result so users can visually identify the property and see exactly which photos were used for each room's AI analysis.

## Scope

- [x] Display 1–2 general/hero images at the top of the results (between the header and the summary)
- [x] Display a horizontally-scrollable image strip inside each room card
- [x] No new API or backend changes — data was already present in the response

## How It Works

### Hero Images

`ResultsDisplay` computes a set of "general" images by filtering `property_data.image_urls` for URLs that do **not** appear in any `room_analyses[].images[]` array. These are typically exterior/facade shots that Apify tagged as non-room categories and the backend excluded from room analysis.

- If ≥ 2 general images are found, use the first 2.
- If fewer than 2 are found, fall back to the first 2 from the full `image_urls` list.
- Rendered in a 1-col (mobile) / 2-col (desktop) responsive grid at `h-48 object-cover`.

### Room Image Strip

Inside `RoomCard`, if `room.images` is non-empty, a `flex overflow-x-auto` container renders all images at `h-28 object-cover`, allowing horizontal scroll when there are many images.

### Image Tags

Plain `<img>` tags are used (not `next/image`) to avoid needing Idealista CDN domains added to `next.config`.

## Decisions

| Decision | Reason |
|---|---|
| Use plain `<img>` over `next/image` | Avoids `next.config` domain whitelist changes for Idealista's CDN |
| Prefer non-room images as hero | Exterior shots give a better first impression than interior room photos |
| Cap hero images at 2 | Keeps the results page compact; the user can see room images per card |
| Horizontal scroll for room images | Rooms can have many images; scroll keeps card height predictable |

## Files Changed

| File | Change |
|---|---|
| `frontend/src/components/ResultsDisplay.tsx` | Added hero images section + room image strip in `RoomCard` |
