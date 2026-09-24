# Changelog

## [0.2.0](https://github.com/faering/jarvis/compare/agent-v0.1.0...agent-v0.2.0) (2026-09-24)


### Features

* **agent:** add a compute-layer router with an async heavy-LLM route ([0e44aa2](https://github.com/faering/jarvis/commit/0e44aa29b6d5f1b7317f8fc3f63868337dd2ccd1))
* **agent:** add an optional heavy_llm role backend ([0fec4f0](https://github.com/faering/jarvis/commit/0fec4f08436a5bce7b8030a96d75aa9add891501)), closes [#59](https://github.com/faering/jarvis/issues/59)
* **agent:** add role backends for LLM, STT, TTS and Vision ([3632a38](https://github.com/faering/jarvis/commit/3632a382952ad0fc543381ba4400aeaba9b28d90)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** local SQLite state store with local-first providers ([23ee8aa](https://github.com/faering/jarvis/commit/23ee8aae1636e055dc5e04f63bb5e5442af0d6b4)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** non-blocking speech output queue with barge-in ([5cda0ef](https://github.com/faering/jarvis/commit/5cda0efb20e29f5219fef539b015f7cbe91c4fe4)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** serve build provenance at GET /version and as OCI labels ([ddc708c](https://github.com/faering/jarvis/commit/ddc708c93255a6ce314e16e353a22f0c94895ff4)), closes [#28](https://github.com/faering/jarvis/issues/28)


### Bug Fixes

* **agent:** bound in-flight speech turns, not only text chunks ([780b490](https://github.com/faering/jarvis/commit/780b4903a5c1a0a4f495c641b1480bc47375b2c7)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** end turns accepted before start() when closing the speech queue ([b596c1e](https://github.com/faering/jarvis/commit/b596c1e1cb3c230b1ac2f40acaa3431cf80bbe4f)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** keep a configured Faelab provider even when it is falsey ([998bf74](https://github.com/faering/jarvis/commit/998bf74ca1de0b7c07d6438c07ce9d50347d43b5)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** let an older build open a state store with additive migrations ([4c8bdc9](https://github.com/faering/jarvis/commit/4c8bdc9bd30f030223182cf071997eb2fd1543c8)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** let the segmenter's hard cut win over a later boundary ([732a89d](https://github.com/faering/jarvis/commit/732a89da5252b7fd7051770facdb22c5fc3a318d)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** make note search case-insensitive for non-ASCII text ([971a5fe](https://github.com/faering/jarvis/commit/971a5fe952938046c65cb25f66c0436186dc95f6)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** provision a jarvis-owned /data for the state store ([bf88e65](https://github.com/faering/jarvis/commit/bf88e65b10efd736e18170a73c15aa053d2fc18c)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** refuse to restore an empty or schema-less snapshot ([3c82030](https://github.com/faering/jarvis/commit/3c820301e6b820b7613aa992e552904981761b26)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** refuse to snapshot onto the live database file ([868d0a1](https://github.com/faering/jarvis/commit/868d0a12c0578eb8c5497540db1591eafdb75447)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** reject non-string replies and streams cut before [DONE] ([bfe0d23](https://github.com/faering/jarvis/commit/bfe0d23b1464fe0813b16c63be91bc209214235a)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** return no events for an empty calendar range ([939b968](https://github.com/faering/jarvis/commit/939b96811813d57da9347358a2ef7915bb5a9684)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** roll back when a state store COMMIT fails ([0944a60](https://github.com/faering/jarvis/commit/0944a60e48f1dca1f7950b65794dc6a998240a13)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** validate and migrate a snapshot before it replaces the live store ([363dec4](https://github.com/faering/jarvis/commit/363dec44b151bcce0e2fcc6d48c3d08d72a63bef)), closes [#75](https://github.com/faering/jarvis/issues/75)


### Documentation

* **agent:** note /version reports the agent's own version ([ff38c78](https://github.com/faering/jarvis/commit/ff38c78cb0c096d946a4c18e7f8c6e55ec48dbdd)), closes [#33](https://github.com/faering/jarvis/issues/33)


### Tests

* **agent:** aclose ends turns queued before start() ([18f044d](https://github.com/faering/jarvis/commit/18f044df10554196fd7cabbc8f9e02bb3501a41b)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** add opt-in live test against the local model stack ([0821041](https://github.com/faering/jarvis/commit/082104117ceb0bf6bbdfddb39aeb56e023d47389)), closes [#57](https://github.com/faering/jarvis/issues/57)
* **agent:** check /version, hello and OCI labels in the container smoke test ([093ef08](https://github.com/faering/jarvis/commit/093ef083fd081621029d0e930e4abe7df2dad1e4)), closes [#28](https://github.com/faering/jarvis/issues/28)
* **agent:** cover empty-snapshot restore and Unicode note search ([f16cb2c](https://github.com/faering/jarvis/commit/f16cb2c1cb769fad4bcf7a4ca84fdff86a7016c8)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** cover non-string replies and streams without [DONE] ([e48f4f8](https://github.com/faering/jarvis/commit/e48f4f8b453d3c389df64210a0c50c00e0f50535)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** cover role backends, env config and factory ([a50d914](https://github.com/faering/jarvis/commit/a50d914841593c5494122499e55f8268381ad5cb)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** cover routing policy, layer fallback and heavy_llm config ([2711329](https://github.com/faering/jarvis/commit/271132960efb3008879c49a0c4438f790619fb2d))
* **agent:** cover speech queue segmentation, pipelining and barge-in ([a951701](https://github.com/faering/jarvis/commit/a9517011f48a40def978395eed9ecf0665ed14c6)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** cover the segmenter hard cut and bounded speech turns ([e65d80b](https://github.com/faering/jarvis/commit/e65d80b78cd65f11474bd6a804187a2032e5ca56)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** cover the state store providers, migrations and snapshots ([fae5aed](https://github.com/faering/jarvis/commit/fae5aeda3d3d557a7df91ec4fae10580336d5876)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** don't require multiple stream chunks in the live test ([db7ba02](https://github.com/faering/jarvis/commit/db7ba02fbab89bb3f56da261111b975500a34a37)), closes [#57](https://github.com/faering/jarvis/issues/57)
* **agent:** set build provenance via the environment in the smoke test ([66df927](https://github.com/faering/jarvis/commit/66df9278ac90894fb95bafaf8d15016410bed664)), closes [#28](https://github.com/faering/jarvis/issues/28)
* **agent:** snapshot refuses the live database path ([dc12323](https://github.com/faering/jarvis/commit/dc123231ee65d435cf4eb7ddf9079ca366810b0c)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** start only the agent service in the container smoke test ([9043688](https://github.com/faering/jarvis/commit/90436887728cbf44ff751ae7acbcd7e914e9164e)), closes [#57](https://github.com/faering/jarvis/issues/57)

## 0.1.0 (2026-09-23)


### Features

* **agent:** add agent service skeleton with WebSocket API ([1b7b3fd](https://github.com/faering/jarvis/commit/1b7b3fd15d365f7601fb275d3be3bbc8bfdf1578)), closes [#24](https://github.com/faering/jarvis/issues/24)


### Bug Fixes

* **agent:** require protocol version and reply to binary frames ([fa45f7a](https://github.com/faering/jarvis/commit/fa45f7ab96f052d850936c5a72e5fae080cfbf58)), closes [#24](https://github.com/faering/jarvis/issues/24)


### Tests

* **agent:** add container integration smoke test ([e94e729](https://github.com/faering/jarvis/commit/e94e72956873c485103bfe8e81c1f7ddf92edad4))
* **agent:** cover missing/non-int v and binary frames ([b8c0746](https://github.com/faering/jarvis/commit/b8c0746f8d92f70b10e5129ced20121450790ec9)), closes [#24](https://github.com/faering/jarvis/issues/24)
* **agent:** make container smoke test opt-in and devcontainer-aware ([f989f71](https://github.com/faering/jarvis/commit/f989f713878fe17527e55063b721889b11d8a446)), closes [#24](https://github.com/faering/jarvis/issues/24)
