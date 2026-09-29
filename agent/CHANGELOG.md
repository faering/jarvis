# Changelog

## [0.5.1](https://github.com/faering/jarvis/compare/agent-v0.5.0...agent-v0.5.1) (2026-09-29)


### Bug Fixes

* **agent:** the playground's reply stats are comma-separated ([a8205df](https://github.com/faering/jarvis/commit/a8205dfabdd7e303bf02e5fbecc535577c466b7c))

## [0.5.0](https://github.com/faering/jarvis/compare/agent-v0.4.0...agent-v0.5.0) (2026-09-28)


### Features

* **agent:** the home Pi uses qwen2.5-1.5b; models pull --assigned ([199d293](https://github.com/faering/jarvis/commit/199d293d6e51e71308991cb8e1ec914847bd5f27)), closes [#159](https://github.com/faering/jarvis/issues/159)

## [0.4.0](https://github.com/faering/jarvis/compare/agent-v0.3.0...agent-v0.4.0) (2026-09-28)


### Features

* **agent:** playground tries uncatalogued models, answers without thinking, notes CPU temperature ([494e80b](https://github.com/faering/jarvis/commit/494e80b552802690889eefd972783f5ca636b5ac)), closes [#159](https://github.com/faering/jarvis/issues/159)

## [0.3.0](https://github.com/faering/jarvis/compare/agent-v0.2.0...agent-v0.3.0) (2026-09-28)


### Features

* **agent:** model catalogue with per-device role assignment ([27bf785](https://github.com/faering/jarvis/commit/27bf7857fddb3faf86a812b46f81dc3ca1150c79)), closes [#56](https://github.com/faering/jarvis/issues/56)
* **agent:** model playground to list, pull, chat with and bench models ([304adea](https://github.com/faering/jarvis/commit/304adea9ac2417ad918b16ae0db594b41663fa77)), closes [#56](https://github.com/faering/jarvis/issues/56)

## [0.2.0](https://github.com/faering/jarvis/compare/agent-v0.1.0...agent-v0.2.0) (2026-09-27)


### Features

* **agent:** add a compute-layer router with an async heavy-LLM route ([0e44aa2](https://github.com/faering/jarvis/commit/0e44aa29b6d5f1b7317f8fc3f63868337dd2ccd1))
* **agent:** add an optional heavy_llm role backend ([0fec4f0](https://github.com/faering/jarvis/commit/0fec4f08436a5bce7b8030a96d75aa9add891501)), closes [#59](https://github.com/faering/jarvis/issues/59)
* **agent:** add capability manifests and provider resolution ([479f037](https://github.com/faering/jarvis/commit/479f0378a0a523336a9756f99f807fafd1793afe)), closes [#72](https://github.com/faering/jarvis/issues/72)
* **agent:** add layered config with profiles and auto hardware probing ([559e716](https://github.com/faering/jarvis/commit/559e716e23eb654e7dcdbd5f6a91903ba87af77e)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** add role backends for LLM, STT, TTS and Vision ([3632a38](https://github.com/faering/jarvis/commit/3632a382952ad0fc543381ba4400aeaba9b28d90)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** always-on voice loop wired into the agent runtime ([3bf820f](https://github.com/faering/jarvis/commit/3bf820f6f6a89bee29fb67e10e4f70fc1613ed3c)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** local SQLite state store with local-first providers ([23ee8aa](https://github.com/faering/jarvis/commit/23ee8aae1636e055dc5e04f63bb5e5442af0d6b4)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** non-blocking speech output queue with barge-in ([5cda0ef](https://github.com/faering/jarvis/commit/5cda0efb20e29f5219fef539b015f7cbe91c4fe4)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** optional trace_id on turn frames (state, transcript, reply, error) ([ad0c963](https://github.com/faering/jarvis/commit/ad0c963d241455c7e1bd803de44f73cdbe968ccb)), closes [#126](https://github.com/faering/jarvis/issues/126)
* **agent:** print resolved config and capabilities with python -m jarvis_agent.config ([4d3d13a](https://github.com/faering/jarvis/commit/4d3d13a80d9d103458f32913f614466d582a2bba)), closes [#73](https://github.com/faering/jarvis/issues/73) [#72](https://github.com/faering/jarvis/issues/72)
* **agent:** send the loop's current state to a newly connected client ([b753c45](https://github.com/faering/jarvis/commit/b753c456c68fb685e153e7824b0ab4e48e1b3c42)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** serve build provenance at GET /version and as OCI labels ([ddc708c](https://github.com/faering/jarvis/commit/ddc708c93255a6ce314e16e353a22f0c94895ff4)), closes [#28](https://github.com/faering/jarvis/issues/28)
* **agent:** spec logging with per-turn trace ids ([fd168d0](https://github.com/faering/jarvis/commit/fd168d02bc920011939b9c2388316e2e9290b0c6)), closes [#126](https://github.com/faering/jarvis/issues/126)


### Bug Fixes

* **agent:** accept unknown say fields; flag a dropped apology as unspoken ([747622b](https://github.com/faering/jarvis/commit/747622b1ee0ddbce6329be9bcb4c0db01b05a375)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** bound in-flight speech turns, not only text chunks ([780b490](https://github.com/faering/jarvis/commit/780b4903a5c1a0a4f495c641b1480bc47375b2c7)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** bound voice loop input and flag partially dropped speech ([af479b5](https://github.com/faering/jarvis/commit/af479b53353715d53df469dbc3cde480e9bffcba)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** check capabilities given as an empty table ([9097df2](https://github.com/faering/jarvis/commit/9097df220ee52654e37e0b7e38e661519beba934)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** end turns accepted before start() when closing the speech queue ([b596c1e](https://github.com/faering/jarvis/commit/b596c1e1cb3c230b1ac2f40acaa3431cf80bbe4f)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** flag replies whose speech already failed as not spoken ([b3fa04f](https://github.com/faering/jarvis/commit/b3fa04f7f80b07e2095670aeb6930dec37af3bc7)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** keep a configured Faelab provider even when it is falsey ([998bf74](https://github.com/faering/jarvis/commit/998bf74ca1de0b7c07d6438c07ce9d50347d43b5)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** keep voice loop state in the actor and bound offloaded work ([ce23f55](https://github.com/faering/jarvis/commit/ce23f55e3ae870f10488b0b3847fe17bb4d8dff9)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** let an older build open a state store with additive migrations ([4c8bdc9](https://github.com/faering/jarvis/commit/4c8bdc9bd30f030223182cf071997eb2fd1543c8)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** let the segmenter's hard cut win over a later boundary ([732a89d](https://github.com/faering/jarvis/commit/732a89da5252b7fd7051770facdb22c5fc3a318d)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** make note search case-insensitive for non-ASCII text ([971a5fe](https://github.com/faering/jarvis/commit/971a5fe952938046c65cb25f66c0436186dc95f6)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** name the config layer in unknown capability errors ([83d00e5](https://github.com/faering/jarvis/commit/83d00e5d72c160df08b7c605e6604009290d50b5)), closes [#72](https://github.com/faering/jarvis/issues/72)
* **agent:** provision a jarvis-owned /data for the state store ([bf88e65](https://github.com/faering/jarvis/commit/bf88e65b10efd736e18170a73c15aa053d2fc18c)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** raise sqlite3 errors from SqliteStore.run as StoreError ([a00ab53](https://github.com/faering/jarvis/commit/a00ab53eb927d099f9cd014baaec2d331b0678ba)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** refuse to restore an empty or schema-less snapshot ([3c82030](https://github.com/faering/jarvis/commit/3c820301e6b820b7613aa992e552904981761b26)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** refuse to snapshot onto the live database file ([868d0a1](https://github.com/faering/jarvis/commit/868d0a12c0578eb8c5497540db1591eafdb75447)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** reject non-string replies and streams cut before [DONE] ([bfe0d23](https://github.com/faering/jarvis/commit/bfe0d23b1464fe0813b16c63be91bc209214235a)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** report a config file with invalid UTF-8 as a ConfigError ([3c6e16d](https://github.com/faering/jarvis/commit/3c6e16d083f2c7207c737dd82d5e7e3f2220147c)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** return no events for an empty calendar range ([939b968](https://github.com/faering/jarvis/commit/939b96811813d57da9347358a2ef7915bb5a9684)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** roll back when a state store COMMIT fails ([0944a60](https://github.com/faering/jarvis/commit/0944a60e48f1dca1f7950b65794dc6a998240a13)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** treat any probe exception as hardware absent ([ac04a90](https://github.com/faering/jarvis/commit/ac04a903ba6aa43a6becd5fc09a71ba736228c7b)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** validate and migrate a snapshot before it replaces the live store ([363dec4](https://github.com/faering/jarvis/commit/363dec44b151bcce0e2fcc6d48c3d08d72a63bef)), closes [#75](https://github.com/faering/jarvis/issues/75)


### Documentation

* **agent:** note /version reports the agent's own version ([ff38c78](https://github.com/faering/jarvis/commit/ff38c78cb0c096d946a4c18e7f8c6e55ec48dbdd)), closes [#33](https://github.com/faering/jarvis/issues/33)


### Tests

* **agent:** aclose ends turns queued before start() ([18f044d](https://github.com/faering/jarvis/commit/18f044df10554196fd7cabbc8f9e02bb3501a41b)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** add opt-in live test against the local model stack ([0821041](https://github.com/faering/jarvis/commit/082104117ceb0bf6bbdfddb39aeb56e023d47389)), closes [#57](https://github.com/faering/jarvis/issues/57)
* **agent:** an empty capability table is still validated ([4108e17](https://github.com/faering/jarvis/commit/4108e17e291b473599c33c796fa26cf147763c7f)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** check /version, hello and OCI labels in the container smoke test ([093ef08](https://github.com/faering/jarvis/commit/093ef083fd081621029d0e930e4abe7df2dad1e4)), closes [#28](https://github.com/faering/jarvis/issues/28)
* **agent:** check enum, pattern, const and oneOf in the schema conformance test ([5318a94](https://github.com/faering/jarvis/commit/5318a949ae5858c836bbcca15efe3a331de9ffef)), closes [#32](https://github.com/faering/jarvis/issues/32)
* **agent:** check the protocol against the shared schema ([27b5c52](https://github.com/faering/jarvis/commit/27b5c5221d00c90e005d35e71dd02beb1745f29c)), closes [#32](https://github.com/faering/jarvis/issues/32)
* **agent:** cover empty-snapshot restore and Unicode note search ([f16cb2c](https://github.com/faering/jarvis/commit/f16cb2c1cb769fad4bcf7a4ca84fdff86a7016c8)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** cover layered config, hardware probes and capability resolution ([8906020](https://github.com/faering/jarvis/commit/8906020824df4ade35621a0aa3136403f35d1309)), closes [#73](https://github.com/faering/jarvis/issues/73) [#72](https://github.com/faering/jarvis/issues/72)
* **agent:** cover non-string replies and streams without [DONE] ([e48f4f8](https://github.com/faering/jarvis/commit/e48f4f8b453d3c389df64210a0c50c00e0f50535)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** cover role backends, env config and factory ([a50d914](https://github.com/faering/jarvis/commit/a50d914841593c5494122499e55f8268381ad5cb)), closes [#58](https://github.com/faering/jarvis/issues/58)
* **agent:** cover routing policy, layer fallback and heavy_llm config ([2711329](https://github.com/faering/jarvis/commit/271132960efb3008879c49a0c4438f790619fb2d))
* **agent:** cover speech queue segmentation, pipelining and barge-in ([a951701](https://github.com/faering/jarvis/commit/a9517011f48a40def978395eed9ecf0665ed14c6)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** cover the input bound and chunk-dropped replies ([9656dd5](https://github.com/faering/jarvis/commit/9656dd589c33220894c438b5ac2eaf739eac6b6b)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** cover the segmenter hard cut and bounded speech turns ([e65d80b](https://github.com/faering/jarvis/commit/e65d80b78cd65f11474bd6a804187a2032e5ca56)), closes [#26](https://github.com/faering/jarvis/issues/26)
* **agent:** cover the state store providers, migrations and snapshots ([fae5aed](https://github.com/faering/jarvis/commit/fae5aeda3d3d557a7df91ec4fae10580336d5876)), closes [#75](https://github.com/faering/jarvis/issues/75)
* **agent:** cover the voice loop, runtime lifespan and WebSocket say ([e640f8a](https://github.com/faering/jarvis/commit/e640f8acef25c00c970544df0b6316a383e01c0a)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** cover unstorable replies and failed speech in the voice loop ([d99d86e](https://github.com/faering/jarvis/commit/d99d86ed2c4a9cc8d73d33aeb8fedb10da941b9f)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** don't require multiple stream chunks in the live test ([db7ba02](https://github.com/faering/jarvis/commit/db7ba02fbab89bb3f56da261111b975500a34a37)), closes [#57](https://github.com/faering/jarvis/issues/57)
* **agent:** expect the initial state frame after hello ([47c0eef](https://github.com/faering/jarvis/commit/47c0eefebcec0f2e3c5e72c4814fb6ee7d5a7909)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** invalid UTF-8 in a config file is a ConfigError ([9fd6a28](https://github.com/faering/jarvis/commit/9fd6a28384e31191ace99406ad44ec27221dc0b0)), closes [#73](https://github.com/faering/jarvis/issues/73)
* **agent:** say ignores unknown payload fields ([c8965b7](https://github.com/faering/jarvis/commit/c8965b7c980bacaa68e171b6bbe43b2dfcf1325e)), closes [#27](https://github.com/faering/jarvis/issues/27)
* **agent:** set build provenance via the environment in the smoke test ([66df927](https://github.com/faering/jarvis/commit/66df9278ac90894fb95bafaf8d15016410bed664)), closes [#28](https://github.com/faering/jarvis/issues/28)
* **agent:** skip agent-pushed events while waiting for pong in the container smoke test ([df8fad2](https://github.com/faering/jarvis/commit/df8fad24b2592a2199326d1dc4928948e69d369e)), closes [#27](https://github.com/faering/jarvis/issues/27)
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
