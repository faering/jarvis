# Changelog

## 0.1.0 (2026-09-24)


### Features

* **app:** connect to the agent over the WebSocket bridge ([dd51ad0](https://github.com/faering/jarvis/commit/dd51ad0666a3ca17daabb7874157e9a4f4333965)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** resolve VITE_APP_VERSION from scripts/version.sh at build time ([75975ab](https://github.com/faering/jarvis/commit/75975ab7dc9740f50b3f77a2c0a88a9e20c53b47)), closes [#33](https://github.com/faering/jarvis/issues/33)
* **app:** scaffold the Tauri app shell ([c277617](https://github.com/faering/jarvis/commit/c27761722a04b152a94eb51f78c61c9b63e6c6a3)), closes [#29](https://github.com/faering/jarvis/issues/29)


### Bug Fixes

* **app:** ignore non-hello frames with a foreign envelope version ([24774ce](https://github.com/faering/jarvis/commit/24774ce7daa181686894fbbf05ddf11fb18aaa8f)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** require the v0 envelope on hello; document the CSP for agent URLs ([0384f51](https://github.com/faering/jarvis/commit/0384f515a7d573fb9ca7fca4c197417d9c2c9154)), closes [#30](https://github.com/faering/jarvis/issues/30)


### Documentation

* **app:** note the header shows the app's own version ([eb17ec2](https://github.com/faering/jarvis/commit/eb17ec2b76425d40729c1b492b07d472f75eee71)), closes [#33](https://github.com/faering/jarvis/issues/33)


### Tests

* **app:** cover a hello with a foreign envelope version ([4755d95](https://github.com/faering/jarvis/commit/4755d958714a03edaaf6fef7fafe83e98028e51d)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** cover a pong with a foreign envelope version ([89a6e15](https://github.com/faering/jarvis/commit/89a6e15a4830fb1da45bf7775cb2f0f7216aa0bd)), closes [#30](https://github.com/faering/jarvis/issues/30)
