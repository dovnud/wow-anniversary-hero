# Handoff: WOW 9-year hero, make the "9" match the WOW logo

Paste this into Claude (claude.ai), and attach: (1) the WOW logo image, (2) the screenshot of wow-vegas.com, (3) the three files in `webflow/` (or `index.html`).
Repo: https://github.com/dovnud/wow-anniversary-hero, branch `claude/new-session-iwa2rb`.

## Goal
A hero for the page wow-vegas.com/9-years. A big "9" stands like an iceberg in animated 3D water, over a photo. **The 9 must look like a letter cut from the WOW logo**, not an approximation. The water is approved. Do not change it.

## The reference (the WOW logo)
- Chunky 3D block letters, dark charcoal/gunmetal with worn, scratched wood and metal texture.
- Deep extrusion; side faces visible on the right and bottom, darker than the face.
- Rows of round orange-amber bulbs set into sockets in the face, following each stroke. Hot yellow core, orange body, dark socket ring, glow spilling onto the letter and glints on the glass.
- Electric cyan neon outline around each letter and its counters, with a jagged lightning-crackle edge and a soft blue halo.
- Subtitle "The Vegas Spectacular" in yellow with a dark teal outline (not needed in the hero).

## Where the current attempt falls short (user: "not close enough")
The current 9 is drawn procedurally in a 2D canvas (`drawNumeral()` in `index.html`) and used as a texture on a flat quad. It reads as flat and clean. Missing or weak:
- Real 3D depth: the extrusion is a stack of offset fills, not lit geometry. No bevels, no light on the side faces, no ambient occlusion in the sockets.
- Materials: face texture is generic noise, not the logo's scratched dark metal and wood.
- Bulbs: flat circles. They need convex glass, specular highlights, a warm bloom, and a slight flicker.
- Neon: a smooth line. The logo's has a jagged crackle edge and stronger bloom.
- The glyph itself: Anton is condensed. The logo's letters are wide and heavy. A wider, heavier letterform (or a custom path) would match better.

## Suggested approach
Build the 9 as real Three.js geometry in the same scene as the water (`ExtrudeGeometry` from the glyph outline, bevel on, dark metallic `MeshStandardMaterial`), with:
- an emissive instanced mesh for the bulbs, placed along the glyph centerline,
- a cyan neon tube or line along the edge with bloom (UnrealBloomPass, or a cheap additive glow sprite),
- the existing water shader unchanged. It currently reflects the 9 by sampling a canvas texture with analytic ray-plane math (see `numSample` in the water fragment shader). If the 9 becomes true geometry, replace that with a render-to-texture mirror pass, or keep the canvas texture only for the reflection.

If you would rather stay 2D: render the 9 in the canvas with far more detail (bevel highlights, per-bulb specular and bloom, crackle outline, darker lit side faces), and keep the existing texture pipeline.

## Fixed facts (do not change)
- Show: WOW - The Vegas Spectacular, Rio Hotel & Casino, Las Vegas. 9 years at Rio, more than 3,500 performances, millions of guests, this October (month only).
- Schedule: Tuesday through Sunday 7pm, dark Monday. 90 minutes. Open to all ages, recommended 3 and up (never "4+").
- Tickets: Ticketmaster only: https://www.ticketmaster.com/wow-the-vegas-spectacular-tickets/artist/2400683
- "Get Tickets" links there; "Watch the Show" is a same-page anchor to `#watch`.
- Avoid: rounded card grids, tracked-out all-caps eyebrow labels, middle-dot meta strings, a boxed 3-column stat grid. Use the word "iconic" for the milestone framing.

## Brand (from the live site)
- Font: Anton (Google Fonts), uppercase headings.
- Black backgrounds, sky blue (~#73D7FF) and orange (~#FF7A14) accents, deep navy footer. Rectangular, square-cornered buttons. Orange is the ticket CTA, sky blue the secondary button.
- Estimated from a small screenshot; replace with exact hex values if you have them.

## Assets (already hosted)
- Logo: https://cdn.prod.website-files.com/690e7ceeb3d249294ed6993c/690edb91e10d6f318eb156f4_logocolor%20(1).png
- Hero photo: https://cdn.prod.website-files.com/690e7ceeb3d249294ed6993c/6abf11fe688d1d93af401850_wow1-water-hair-email.jpg
- Other photos are listed in the original brief.

## Files
- `index.html`: full test page (open in a browser). Contains everything.
- `webflow/1-head-code.html` (Head code), `2-hero-embed.html` (Embed element), `3-footer-code.html` (Footer code): split for Webflow, since an Embed element is capped at 10,000 characters. Regenerate these from `index.html` after any change. The existing site nav is not included, since the page already has one.
- Constraints: vanilla HTML/CSS/JS, Three.js from a CDN script tag (r159 `three.min.js` from jsDelivr; r160+ removed that build), no build step. The canvas must be transparent so it composites over the photo. Pause rendering when off-screen; support `prefers-reduced-motion` and a CSS fallback if WebGL is unavailable.

## Known environment limits from the previous session
The previous sandbox blocked wow-vegas.com, the Webflow CDN and Google Fonts, so the real photo, logo and Anton were never seen in a render. Please check the 9 against the actual logo and the real hero photo.
