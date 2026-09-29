# Changelog

## [0.1.2](https://github.com/faering/jarvis/compare/app-v0.1.1...app-v0.1.2) (2026-09-29)


### Bug Fixes

* **app:** no middle dot in the reply note or the ambient placeholder ([8920080](https://github.com/faering/jarvis/commit/8920080431e79285100fd5e7213e2102e05f9d33))

## [0.1.1](https://github.com/faering/jarvis/compare/app-v0.1.0...app-v0.1.1) (2026-09-28)


### Bug Fixes

* **app:** render correctly on the Pi, log there by default, open full screen on request ([bbc5f91](https://github.com/faering/jarvis/commit/bbc5f9158cf516f52bcdcfac9154601ef56c48ca)), closes [#167](https://github.com/faering/jarvis/issues/167)

## 0.1.0 (2026-09-27)


### Features

* **app:** connect to the agent over the WebSocket bridge ([dd51ad0](https://github.com/faering/jarvis/commit/dd51ad0666a3ca17daabb7874157e9a4f4333965)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** default-screen prototypes (face, orb, ambient) ([5bef357](https://github.com/faering/jarvis/commit/5bef357e5a55c9f00f1916a6b885a32ce2ffc3ca)), closes [#133](https://github.com/faering/jarvis/issues/133)
* **app:** resolve VITE_APP_VERSION from scripts/version.sh at build time ([75975ab](https://github.com/faering/jarvis/commit/75975ab7dc9740f50b3f77a2c0a88a9e20c53b47)), closes [#33](https://github.com/faering/jarvis/issues/33)
* **app:** Rust logger writing the spec line and the daily file ([b4c341b](https://github.com/faering/jarvis/commit/b4c341b27137698ec2235504f6c2ae04b5b55f62)), closes [#126](https://github.com/faering/jarvis/issues/126)
* **app:** scaffold the Tauri app shell ([c277617](https://github.com/faering/jarvis/commit/c27761722a04b152a94eb51f78c61c9b63e6c6a3)), closes [#29](https://github.com/faering/jarvis/issues/29)
* **app:** TS logger with turn correlation, wired into the agent client and presence ([0ab37f9](https://github.com/faering/jarvis/commit/0ab37f99ed021eb6782814ae5439ca1621507bb4)), closes [#126](https://github.com/faering/jarvis/issues/126)
* **app:** typed conversation shown on every presence screen ([340ea63](https://github.com/faering/jarvis/commit/340ea639a0c091ae0e67b34d607584cd806856b4)), closes [#158](https://github.com/faering/jarvis/issues/158)


### Bug Fixes

* **app:** ignore non-hello frames with a foreign envelope version ([24774ce](https://github.com/faering/jarvis/commit/24774ce7daa181686894fbbf05ddf11fb18aaa8f)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** require the v0 envelope on hello; document the CSP for agent URLs ([0384f51](https://github.com/faering/jarvis/commit/0384f515a7d573fb9ca7fca4c197417d9c2c9154)), closes [#30](https://github.com/faering/jarvis/issues/30)


### Refactoring

* **app:** screen catalogue with one folder per screen, face by default ([da904d7](https://github.com/faering/jarvis/commit/da904d7e40d4cf2d6f069035493cf855f4eddbed)), closes [#133](https://github.com/faering/jarvis/issues/133)
* **app:** use @jarvis/protocol and the shared @jarvis/config ([b14e27d](https://github.com/faering/jarvis/commit/b14e27d0f9ed15cf6fc307f4fa7eae1e5ccd19c5)), closes [#32](https://github.com/faering/jarvis/issues/32)


### Documentation

* **app:** note the header shows the app's own version ([eb17ec2](https://github.com/faering/jarvis/commit/eb17ec2b76425d40729c1b492b07d472f75eee71)), closes [#33](https://github.com/faering/jarvis/issues/33)


### Tests

* **app:** add agent↔app integration suite for the real AgentClient ([6cc5fe1](https://github.com/faering/jarvis/commit/6cc5fe114502ba55722154d97a9b4458318923a1)), closes [#108](https://github.com/faering/jarvis/issues/108)
* **app:** cover a hello with a foreign envelope version ([4755d95](https://github.com/faering/jarvis/commit/4755d958714a03edaaf6fef7fafe83e98028e51d)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** cover a pong with a foreign envelope version ([89a6e15](https://github.com/faering/jarvis/commit/89a6e15a4830fb1da45bf7775cb2f0f7216aa0bd)), closes [#30](https://github.com/faering/jarvis/issues/30)
* **app:** cover presence mapping, demo driver, switcher and variants ([97d296f](https://github.com/faering/jarvis/commit/97d296fe683f75c3caa7b13da75affdb9145eeae)), closes [#133](https://github.com/faering/jarvis/issues/133)
* **app:** ignore agent-pushed events on the raw integration socket ([1ce124d](https://github.com/faering/jarvis/commit/1ce124d5665c87d2bedfb92b7f77e8ae9f37116f)), closes [#108](https://github.com/faering/jarvis/issues/108)
* **app:** pass describe.runIf a real boolean ([f867102](https://github.com/faering/jarvis/commit/f867102cbe48fce42a5fc9f69014228eb69a3e0f)), closes [#108](https://github.com/faering/jarvis/issues/108)
