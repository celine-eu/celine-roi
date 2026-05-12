# CHANGELOG

<!-- version list -->

## v1.10.3 (2026-05-12)

### Bug Fixes

- Update lidar trigger
  ([`ef42d7d`](https://github.com/celine-eu/celine-roi/commit/ef42d7d996b82ac85cdc68bf13755e1879d1e81d))

### Chores

- Update docs
  ([`5297618`](https://github.com/celine-eu/celine-roi/commit/5297618eb11a464ff273ca136ad496e9f4bd350f))


## v1.10.2 (2026-04-29)

### Bug Fixes

- Use sync conn in alembic
  ([`81e83fd`](https://github.com/celine-eu/celine-roi/commit/81e83fd28e872a40cb34f9f3043ac33d33b73928))


## v1.10.1 (2026-04-29)

### Bug Fixes

- Add logging, switch default db name
  ([`acdc91e`](https://github.com/celine-eu/celine-roi/commit/acdc91e3461a2cc6718ad870ee672786351d31de))


## v1.10.0 (2026-04-29)

### Chores

- **deps**: Bump fastapi from 0.135.2 to 0.136.1
  ([`04084b6`](https://github.com/celine-eu/celine-roi/commit/04084b62964c93a59c7df653e272778b35994ddb))

- **deps**: Bump pydantic from 2.12.5 to 2.13.3
  ([`c972e5c`](https://github.com/celine-eu/celine-roi/commit/c972e5c78aa8f4c718293835f532b23c91c6b5f8))

- **deps**: Bump the runtime-dependencies group across 1 directory with 3 updates
  ([`9dc3033`](https://github.com/celine-eu/celine-roi/commit/9dc30338aa3804203923b0bb09468d6d37b0ddc9))

- **deps**: Update uvicorn[standard] requirement
  ([`24a0813`](https://github.com/celine-eu/celine-roi/commit/24a08130915ff3541c963be58b68e1e8c4a87cfd))

- **deps-dev**: Bump the development-dependencies group across 1 directory with 4 updates
  ([`d85e550`](https://github.com/celine-eu/celine-roi/commit/d85e550b60576ddfae5cef83b3275e3fb0e47fc0))

### Continuous Integration

- Bump the actions group across 1 directory with 3 updates
  ([`3bfcd49`](https://github.com/celine-eu/celine-roi/commit/3bfcd49af7e8c1c517ff4dc852332e6197033e03))

### Features

- Add alembic, AGENTS.md
  ([`7a6e734`](https://github.com/celine-eu/celine-roi/commit/7a6e7340d41c9d3e203106b57887e40a8f8ac6e8))


## v1.9.2 (2026-04-27)

### Bug Fixes

- Strip asincpg from DATABASE
  ([`38c4e5d`](https://github.com/celine-eu/celine-roi/commit/38c4e5db75c927944a927652f78d9d8b0bbf73a3))


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
