# CHANGELOG

<!-- version list -->

## v1.9.1 (2026-04-27)

### Bug Fixes

- Add readme
  ([`4248b4a`](https://github.com/celine-eu/celine-roi/commit/4248b4a028e2b1ad7e0162f8086e9f09bd72f873))


## v1.9.0 (2026-04-27)

### Bug Fixes

- **estimates**: Fix event loop mismatch in TestEstimatesAPI tests
  ([`3ac0b88`](https://github.com/celine-eu/celine-roi/commit/3ac0b8811565b52b6e75d3c7b2cb3d727ebbf9d8))

- **estimates**: Patch save_estimate on route modules, not database module
  ([`e7acfeb`](https://github.com/celine-eu/celine-roi/commit/e7acfeb44295a967cc921ee33400b4f1173e01c9))

### Chores

- Add dependabot
  ([`b0456f4`](https://github.com/celine-eu/celine-roi/commit/b0456f4473554b87edf62ad14b873707348cf858))

- Update uv.lock
  ([`06f3923`](https://github.com/celine-eu/celine-roi/commit/06f3923f2ef6a53e6b60a7844b0840a6a56adafc))

- Use release template
  ([`6381247`](https://github.com/celine-eu/celine-roi/commit/638124749a7f0b8881d84ce59921e129737cfd08))

### Code Style

- Fix ruff and black formatting for estimates feature
  ([`c66b783`](https://github.com/celine-eu/celine-roi/commit/c66b78330d8d9599e1b6f832a3d5aa65bc8c7d6b))

### Features

- **estimates**: Add database module with save/get/list + tests
  ([`a91a4c0`](https://github.com/celine-eu/celine-roi/commit/a91a4c03c4ebcf8d3db96054f4cf1bfa9f8bffa1))

- **estimates**: Add DDL schema and asyncpg dependency
  ([`7afb474`](https://github.com/celine-eu/celine-roi/commit/7afb474f8627193ffe124beb7a66769beaaac5ab))

- **estimates**: Add GET /estimates endpoints and wire pool into lifespan
  ([`bacad5f`](https://github.com/celine-eu/celine-roi/commit/bacad5f013d81b0cda79a80f4e4abbeca27f7658))

- **estimates**: Persist /scenario and /compare calls via BackgroundTasks
  ([`a12af58`](https://github.com/celine-eu/celine-roi/commit/a12af5853b4a7df86c2005b45ac3f56f4a463acf))


## v1.0.0 (2026-04-07)

- Initial Release
