# Design System Document: The Intelligence of Light

## 1. Overview & Creative North Star
**Creative North Star: "The Ethereal Core"**

This design system moves away from the rigid, boxy layouts of traditional desktop software. Instead, it treats the interface as a living, breathing entity. The "Ethereal Core" philosophy balances the cold precision of high-tech AI with the fluid, organic nature of human voice. 

We break the "template" look through **Intentional Asymmetry** and **Atmospheric Depth**. By utilizing wide margins, overlapping "glass" panels, and a focus on tonal layering rather than lines, we create an environment that feels premium, secure, and infinitely responsive. The goal is not just to display data, but to house an intelligence.

---

## 2. Colors
Our palette is rooted in the deep shadows of the cosmos (`#060e20`), punctuated by the electric pulse of neural activity (`#b6a0ff` and `#00e3fd`).

### The "No-Line" Rule
**Explicit Instruction:** 1px solid borders are strictly prohibited for sectioning. 
Structure must be defined through background shifts. For example, a sidebar should be `surface-container-low`, while the main workspace sits on the `surface` background. This creates a "soft-edge" architecture that feels more modern and less utilitarian.

### Surface Hierarchy & Nesting
Depth is achieved through the physical stacking of tones:
- **Base Layer:** `surface` (#060e20)
- **Secondary Workspaces:** `surface-container-low` (#091328)
- **Interactive Cards/Panels:** `surface-container-high` (#141f38)
- **Floating Modals:** `surface-container-highest` (#192540)

### The "Glass & Gradient" Rule
To elevate the UI, floating elements must utilize **Glassmorphism**. Combine `surface-container-highest` at 60% opacity with a `backdrop-filter: blur(20px)`. 

### Signature Textures
Main CTAs and the Voice Visualizer must use a **Linear Pulse Gradient**: 
`linear-gradient(135deg, #b6a0ff 0%, #70aaff 100%)`. This provides a visual "soul" that flat colors cannot replicate.

---

## 3. Typography
The system uses a dual-sans-serif approach to balance high-tech precision with editorial authority.

*   **Display & Headline (Manrope):** Chosen for its geometric purity and modern proportions. Large scales (`display-lg` at 3.5rem) should be used with tight letter-spacing to command attention during "listening" states.
*   **Body & Labels (Inter):** The workhorse. Inter provides maximum legibility for AI transcripts and system logs. Use `body-md` (0.875rem) as the standard for chat bubbles to maintain a compact, desktop-optimized density.

**Identity Through Scale:** Use extreme contrast. Pair a `display-sm` greeting ("Good morning") with a `label-sm` timestamp to create a sophisticated, "magazine-style" layout that feels custom-built.

---

## 4. Elevation & Depth
We eschew traditional "Drop Shadows" in favor of **Tonal Layering**.

*   **The Layering Principle:** Instead of a shadow, place a `surface-container-lowest` (#000000) card inside a `surface-container-low` section to create "sunken" depth. Place a `surface-container-high` card on `surface` to create "raised" depth.
*   **Ambient Shadows:** If a floating state is required (e.g., a context menu), use a shadow with a 40px blur and 6% opacity. The shadow color must be `#000000`, never a neutral grey, to maintain the richness of the deep blue background.
*   **The "Ghost Border" Fallback:** If accessibility requires a container definition, use the `outline-variant` (#40485d) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Voice Visualizer (Signature Component)
The centerpiece of the app. It should never be a static bar. 
*   **Active State:** Uses `secondary` (#00e3fd) and `tertiary` (#70aaff) in an overlapping wave pattern.
*   **Blur:** Apply a `secondary_container` outer glow to simulate light emission.

### Buttons
*   **Primary:** Solid `primary` (#b6a0ff) with `on_primary` (#34000) text. Corner radius: `full`.
*   **Secondary (Glass):** `surface-container-high` at 40% opacity with a `backdrop-filter`. This makes the button feel like part of the interface rather than an appended box.

### Input Fields (Chat/Command)
*   **Structure:** No background stroke. Use `surface-container-highest` background. 
*   **Focus State:** Transition the background to a subtle gradient of `surface-container-highest` to `surface-bright`.

### Cards & Lists
*   **The "No-Divider" Rule:** Forbid 1px dividers. Separate list items using 8px of vertical whitespace or by alternating between `surface` and `surface-container-low`.
*   **Radius:** Cards must use `xl` (1.5rem) for the outer container and `md` (0.75rem) for internal nested elements (like images or mini-charts).

### Transcription Chips
*   **Status:** Use `tertiary` for processed text and `on_surface_variant` for "thinking" or low-confidence text.
*   **Shape:** `md` (0.75rem) for a modern, slightly-squared-off look that fits desktop density.

---

## 6. Do's and Don'ts

### Do
*   **Do** use wide gutters (32px+) to give the AI's responses "breathing room."
*   **Do** use the `secondary` (#00e3fd) color sparingly—only for moments of active communication or confirmation.
*   **Do** overlap elements. A floating glass player slightly overlapping a content section creates a sense of sophisticated layering.

### Don't
*   **Don't** use pure white (#FFFFFF) for text. Always use `on_surface` (#dee5ff) to reduce eye strain in the dark environment.
*   **Don't** use standard 4px or 8px "Material" shadows. They look "cheap" in a high-tech dark mode. 
*   **Don't** use sharp 90-degree corners. Even for desktop, the minimum radius should be `sm` (0.25rem) to maintain the "Responsive & Intelligent" brand personality.