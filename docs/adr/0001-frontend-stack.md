# 0001. Frontend stack
Status: Accepted · Date: 2026-09-23

## Context
The display is a native Tauri app on the Pi 5. We asked two questions: should the webview
frontend also be Rust, and should the UI be a native Rust GUI instead of a webview?

## Decision
- **React/TS in the Tauri webview.** Rust stays in the thin Tauri backend (window and OS glue).
- **Ship v1 on this stack.** A native Rust GUI (Slint) is a possible later swap, but only if
  a hardware spike justifies it. The UI talks to the agent only over the WebSocket, so the
  layer stays swappable.

## Alternatives
- **Rust frontend in WASM (Leptos, Dioxus, Yew):** rejected.
  - The real logic lives in the Python agent, so we would still have three languages.
  - The frameworks are younger, and touch handling, animation and charts would have to be
    built by hand.
  - Rust→WASM compiles are slower than Vite hot reload.
  - No performance gain: it renders in WebKitGTK either way.
- **Native Rust GUI:** deferred.
  - Slint looks most polished for touch. iced is an alternative. egui looks like a tool,
    not a product.
  - Upsides: tens of MB of RAM instead of hundreds, faster boot-to-UI, and smoother
    animation. Slint can render straight to KMS with no compositor, and WebKitGTK's GPU
    acceleration on the Pi can be patchy.
  - Downsides: no npm component or chart ecosystem, slower layout iteration, and weaker
    built-in touch polish.
  - Slint's licence for embedded use needs checking before adopting it.

## Consequences
- The fast React ecosystem and iteration loop are available.
- Heavy CSS effects (blur, large animations) may stutter on the Pi; keep them light.
- If we want more Rust, the better place is the deferred v2 real-time hardware middleware,
  not the UI.

## Revisit when
A hardware test prototypes one screen in Slint on the Pi 5 and compares boot-to-UI time,
idle RAM, animation FPS and touch feel against the webview, and the numbers justify
switching. The test is post-v1 and not scheduled yet.
