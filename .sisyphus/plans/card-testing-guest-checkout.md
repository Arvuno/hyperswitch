# Card Testing Guard: IP-Only Blocking for Guest Checkout

## TL;DR

> **Quick Summary**: Extend the card testing guard to support pure IP-based blocking, addressing the vulnerability where attackers rotate card numbers from the same IP during guest checkout. Also add X-Forwarded-For parsing with trusted proxy config and atomic Redis increments for the new counter.
> 
> **Deliverables**:
> - IP-only blocking strategy within card_testing_guard (independent enable flag, threshold default=10)
> - X-Forwarded-For parsing with server-level trusted proxy configuration
> - Atomic increment for new IP-only counter (Lua script)
> - Server-side IP extraction for IP-only blocking (NOT browser_info.ip_address)
> - Unit tests for card_testing_guard module
> - Updated API config model and cypress integration tests
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Config types → IP extraction → Guard validation → Integration → Tests

---

## Context

### Original Request
User has card testing guard that requires customer_id for some blocking strategies. In guest checkout (no customer_id), the current approach doesn't adequately prevent card testing attacks because an attacker can rotate card numbers from the same IP and bypass both `card_ip_blocking` (different card = different fingerprint) and `guest_user_card_blocking` (different card = different fingerprint). Need IP-only blocking.

### Interview Summary
**Key Discussions**:
- **Strategy design**: Extend existing `card_ip_blocking` with an independent `ip_only_blocking_enabled` flag (not a 4th strategy)
- **IP source**: Use server-side IP extraction (req.connection_info + X-Forwarded-For), NOT browser_info.ip_address which is client-provided and spoofable
- **Blocking scope**: Per business profile, applied to ALL payment attempts (not just guest checkout)
- **Threshold**: IP-only default = 10 (conservative, accounts for shared IPs)
- **Atomic increment**: Fix only the new IP-only counter; existing strategies' race condition is a separate concern
- **Trusted proxies**: Server-level TOML config (infrastructure concern, not merchant concern)
- **X-Forwarded-For**: Required for production correctness behind CDN/proxy
- **Out of scope**: Dashboard UI, CAPTCHA, alerts/notifications, geo-blocking, fixing existing strategies' race condition

**Research Findings**:
- Current guard has 3 strategies: card_ip_blocking (fingerprint+IP), guest_user_card_blocking (fingerprint), customer_id_blocking (customer_id)
- IP currently from `browser_info.ip_address` (spoofable!) or `req.connection_info().realip_remote_addr()` (no X-Forwarded-For)
- Redis increment is GET→SET (not atomic) — will use Lua script for new counter
- No existing tests for card_testing_guard module
- CardTestingGuardConfig stored as JSONB — new fields need Default impl update, no DB migration
- Existing X-Forwarded-For parsing in `dashboard_metadata.rs` takes first IP (wrong for security — should take rightmost untrusted)
- Fred backend has `evaluate_redis_script` for Lua scripts

### Metis Review
**Identified Gaps** (addressed):
- IP source security gap (browser_info.ip_address is spoofable) → Using server-side IP only
- Atomic fix scope (fixing existing strategies risky during deploy) → Fix new counter only
- IP-only Redis key must include profile_id to prevent cross-merchant interference
- IPv6 addresses in Redis keys need normalization
- Trusted proxy config location → Server-level TOML
- Backward compatibility → Default impl handles missing fields

---

## Work Objectives

### Core Objective
Add IP-only blocking to the card testing guard so that an attacker cannot bypass protection by rotating card numbers from the same IP address during guest checkout (or any payment flow).

### Concrete Deliverables
- New fields in `CardTestingGuardConfig`: `is_ip_only_blocking_enabled`, `ip_only_blocking_threshold`
- New Redis key prefix: `IP_ONLY_BLOCKING_CACHE_KEY_PREFIX`
- New validation function: `validate_ip_only_blocking_for_business_profile`
- Server-side IP extraction with X-Forwarded-For parsing and trusted proxy config
- Atomic increment via Lua script for IP-only counter
- Unit tests for card_testing_guard module
- Updated Cypress integration tests

### Definition of Done
- [ ] Merchant can enable/disable IP-only blocking independently via business profile config
- [ ] Failed payment attempts from same IP (regardless of card) increment IP-only counter
- [ ] When IP-only threshold exceeded, payment returns `PreconditionFailed` with "Blocked due to suspicious activity"
- [ ] X-Forwarded-For header parsed correctly with trusted proxy validation
- [ ] Server-side IP used (not browser_info.ip_address) for IP-only blocking
- [ ] Existing card_ip_blocking, guest_user_card_blocking, customer_id_blocking strategies unaffected
- [ ] Backward compatible — existing profiles without new fields get defaults (disabled)

### Must Have
- IP-only blocking with independent enable flag and configurable threshold
- Server-side IP extraction (NOT browser_info.ip_address)
- X-Forwarded-For parsing with configurable trusted proxy list
- Atomic increment for IP-only counter
- Business profile ID in IP-only Redis key
- Backward compatibility with existing profiles

### Must NOT Have (Guardrails)
- Do NOT change behavior of existing card_ip_blocking, guest_user_card_blocking, or customer_id_blocking strategies
- Do NOT fix the race condition in existing strategies' increment (separate concern)
- Do NOT use browser_info.ip_address for IP-only blocking (spoofable)
- Do NOT add Dashboard UI changes
- Do NOT add CAPTCHA, geo-blocking, or alerting
- Do NOT refactor existing code to use enum-based strategy pattern
- Do NOT add Forwarded header (RFC 7239) support
- Do NOT change how existing strategies extract IP
- Do NOT modify the payment flow entry points — only modify guard validation logic
- Do NOT add rate limiting middleware
- Do NOT over-abstract or over-engineer — follow existing patterns exactly

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (tokio::test, actix_web::test, wiremock, serial_test)
- **Automated tests**: Tests after implementation
- **Framework**: Rust #[cfg(test)] + tokio::test for unit tests, Cypress for integration
- **Existing tests for module**: NO — will be first tests for card_testing_guard

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Rust unit tests**: Use `cargo test` — assert function behavior, mock Redis via test utilities
- **Integration tests**: Use Cypress — configure guard, make payments, verify block/allow
- **API verification**: Use `curl` — send requests, assert status + response fields

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — config types, constants, IP extraction):
├── Task 1: Add config fields + defaults + API model [quick]
├── Task 2: Add Redis key prefix + Lua script for atomic increment [quick]
├── Task 3: Server-side IP extraction with X-Forwarded-For + trusted proxy config [unspecified-high]
└── Task 4: Add CardTestingGuardData field for IP-only cache key [quick]

Wave 2 (Core logic — validation + increment):
├── Task 5: IP-only blocking validation function (depends: 1, 2, 4) [unspecified-high]
├── Task 6: IP-only counter increment on payment failure (depends: 2, 4) [unspecified-high]
└── Task 7: Wire IP-only validation into card_testing_guard_checks (depends: 5) [unspecified-high]

Wave 3 (Tests + Integration):
├── Task 8: Unit tests for IP-only blocking logic (depends: 5, 7) [deep]
├── Task 9: Update Cypress integration tests (depends: 7) [unspecified-high]
└── Task 10: End-to-end QA verification (depends: 8, 9) [deep]

Wave FINAL (After ALL tasks — parallel review):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: Task 1 → Task 5 → Task 7 → Task 8 → Task 10 → F1-F4
Parallel Speedup: ~50% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | - | 5 | 1 |
| 2 | - | 5, 6 | 1 |
| 3 | - | 5 | 1 |
| 4 | - | 5, 6 | 1 |
| 5 | 1, 2, 3, 4 | 7 | 2 |
| 6 | 2, 4 | 10 | 2 |
| 7 | 5 | 8, 9 | 2 |
| 8 | 5, 7 | 10 | 3 |
| 9 | 7 | 10 | 3 |
| 10 | 8, 9 | F1-F4 | 3 |
| F1-F4 | 10 | - | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **4** - T1 → `quick`, T2 → `quick`, T3 → `unspecified-high`, T4 → `quick`
- **Wave 2**: **3** - T5 → `unspecified-high`, T6 → `unspecified-high`, T7 → `unspecified-high`
- **Wave 3**: **3** - T8 → `deep`, T9 → `unspecified-high`, T10 → `deep`
- **FINAL**: **4** - F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [ ] 1. Add IP-only blocking config fields + defaults + API model

  **What to do**:
  - Add two new fields to `CardTestingGuardConfig` in `crates/diesel_models/src/business_profile.rs` (lines 825-854):
    - `is_ip_only_blocking_enabled: bool` (default: `false`)
    - `ip_only_blocking_threshold: i32` (default: `10`)
  - Add corresponding fields to the API model in `crates/api_models/src/admin.rs` (lines 259-274):
    - `ip_only_blocking_status: CardTestingGuardStatus` (default: `Disabled`)
    - `ip_only_blocking_threshold: i32` (default: `10`)
  - Update `Default` impl in `crates/common_utils/src/consts.rs` (lines 193-212):
    - Add `DEFAULT_IP_ONLY_BLOCKING_ENABLED: bool = false`
    - Add `DEFAULT_IP_ONLY_BLOCKING_THRESHOLD: i32 = 10`
  - Update the conversion between API model and storage model (likely in `crates/diesel_models/src/business_profile.rs` or the admin route handler) to map new fields
  - Verify backward compatibility: existing `CardTestingGuardConfig` JSON in DB without new fields must deserialize with defaults

  **Must NOT do**:
  - Do NOT change existing field names or types
  - Do NOT add a DB migration (JSONB column handles schema evolution)
  - Do NOT refactor the config struct pattern
  - Do NOT modify existing strategy defaults

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward struct field additions following existing patterns
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Task 5
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/diesel_models/src/business_profile.rs:825-854` - Existing `CardTestingGuardConfig` struct with boolean+threshold pairs. Follow the exact same pattern for the two new fields.
  - `crates/api_models/src/admin.rs:259-274` - API model with `CardTestingGuardStatus` enum + threshold pairs. Add new fields following same pattern.
  - `crates/common_utils/src/consts.rs:193-212` - Default constants. Add two new constants following existing naming pattern.

  **API/Type References** (contracts to implement against):
  - `crates/api_models/src/admin.rs:276-280` - `CardTestingGuardStatus` enum (Enabled/Disabled). Use this for API model fields.

  **Test References** (testing patterns to follow):
  - `cypress-tests/cypress/e2e/spec/Payment/52-CardTestingGuard.cy.js` - Existing Cypress test that configures card testing guard. Shows the API field naming convention.

  **WHY Each Reference Matters**:
  - The diesel_models struct shows the exact field naming pattern (`is_*_enabled` + `*_threshold`) to maintain consistency
  - The API model shows the `Status` vs `bool` naming difference between API and storage layers
  - The consts file shows where to add default values and the naming convention for defaults

  **Acceptance Criteria**:

  - [ ] `CardTestingGuardConfig` in diesel_models has `is_ip_only_blocking_enabled: bool` and `ip_only_blocking_threshold: i32`
  - [ ] API model has `ip_only_blocking_status: CardTestingGuardStatus` and `ip_only_blocking_threshold: i32`
  - [ ] Default impl returns `is_ip_only_blocking_enabled: false` and `ip_only_blocking_threshold: 10`
  - [ ] `cargo check -p diesel_models` passes
  - [ ] `cargo check -p api_models` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Config fields compile and have correct defaults
    Tool: Bash
    Preconditions: Code changes are saved
    Steps:
      1. Run `cargo check -p diesel_models -p api_models -p common_utils`
      2. Verify no compilation errors
      3. Grep for `ip_only_blocking` in diesel_models and api_models to confirm fields exist
    Expected Result: All three crates compile successfully; new fields are present
    Failure Indicators: Compilation errors or missing fields
    Evidence: .sisyphus/evidence/task-1-config-fields-compile.txt

  Scenario: Backward compatibility - existing JSON without new fields deserializes
    Tool: Bash (cargo test)
    Preconditions: Config struct changes are saved
    Steps:
      1. Write a quick test (or verify via code review) that JSON like `{"is_card_ip_blocking_enabled": false, "card_ip_blocking_threshold": 3, ...}` without `ip_only_blocking` fields deserializes with defaults
      2. Alternatively, verify the `Default` impl provides the fallback via serde's `#[serde(default)]`
    Expected Result: Existing JSON configs deserialize correctly with `ip_only_blocking_enabled: false, ip_only_blocking_threshold: 10`
    Failure Indicators: Deserialization error or panic
    Evidence: .sisyphus/evidence/task-1-backward-compat.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): add ip_only_blocking config fields`
  - Files: `crates/diesel_models/src/business_profile.rs`, `crates/api_models/src/admin.rs`, `crates/common_utils/src/consts.rs`
  - Pre-commit: `cargo check -p diesel_models -p api_models -p common_utils`

- [ ] 2. Add Redis key prefix + Lua script for atomic increment

  **What to do**:
  - Add new Redis key prefix constant in `crates/router/src/consts.rs` (lines 88-92):
    - `pub const IP_ONLY_BLOCKING_CACHE_KEY_PREFIX: &str = "IP_ONLY_BLOCKING";`
  - Add a new function `increment_ip_only_blocked_count_in_cache` in `crates/router/src/services/card_testing_guard.rs` that uses a Lua script for atomic increment:
    - The Lua script should: GET current value → INCR → ensure TTL is set → return new value
    - Use `evaluate_redis_script` from the fred backend
    - Key format: `IP_ONLY_BLOCKING_{profile_id}_{ip}`
    - If key doesn't exist, initialize to 1 with TTL
    - Handle IPv6 addresses by replacing colons with dashes in the key
  - Add `get_ip_only_blocked_count_from_cache` function (same pattern as existing `get_blocked_count_from_cache`)
  - Add `set_ip_only_blocked_count_in_cache` function (same pattern as existing `set_blocked_count_in_cache`)

  **Must NOT do**:
  - Do NOT modify existing `increment_blocked_count_in_cache` or other existing functions
  - Do NOT add a 4th strategy — this is extending card_ip_blocking
  - Do NOT use GET→SET pattern for the new increment (must be atomic via Lua)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Following existing patterns with a small Lua script addition
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Task 5, Task 6
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/src/services/card_testing_guard.rs:19-77` - Existing `get_blocked_count_from_cache`, `set_blocked_count_in_cache`, `increment_blocked_count_in_cache`. Follow the same function signatures and error handling for the new functions.
  - `crates/router/src/consts.rs:88-92` - Existing cache key prefixes. Add the new prefix following the same naming pattern.

  **API/Type References** (contracts to implement against):
  - `crates/redis_interface/src/module/fred/commands.rs:1155-1172` - `evaluate_redis_script` function signature. This is how to call Lua scripts.
  - `crates/redis_interface/src/test.rs:1795-1827` - Existing Lua script test pattern. Shows how to structure the Lua script and call `evaluate_redis_script`.

  **Test References** (testing patterns to follow):
  - `crates/redis_interface/src/test.rs:1795-1827` - Lua script test. Shows the pattern for testing Lua scripts with Redis.

  **WHY Each Reference Matters**:
  - The existing card_testing_guard service shows the exact function signatures, error types, and return patterns to follow
  - The Lua script pattern from the test file shows how to properly construct and execute Lua scripts via the fred backend
  - The `evaluate_redis_script` API must be called correctly — the reference shows the exact function signature

  **Acceptance Criteria**:

  - [ ] `IP_ONLY_BLOCKING_CACHE_KEY_PREFIX` constant added to `crates/router/src/consts.rs`
  - [ ] `increment_ip_only_blocked_count_in_cache` function added using Lua script
  - [ ] `get_ip_only_blocked_count_from_cache` function added
  - [ ] `set_ip_only_blocked_count_in_cache` function added
  - [ ] Key format is `IP_ONLY_BLOCKING_{profile_id}_{normalized_ip}` where IPv6 colons are replaced with dashes
  - [ ] `cargo check -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: New Redis service functions compile and follow existing patterns
    Tool: Bash
    Preconditions: Code changes are saved
    Steps:
      1. Run `cargo check -p router`
      2. Verify no compilation errors
      3. Grep for `increment_ip_only_blocked_count_in_cache` in services/card_testing_guard.rs to confirm function exists
      4. Grep for `IP_ONLY_BLOCKING_CACHE_KEY_PREFIX` in consts.rs to confirm constant exists
    Expected Result: Router crate compiles; new function and constant are present
    Failure Indicators: Compilation errors or missing definitions
    Evidence: .sisyphus/evidence/task-2-redis-service-compile.txt

  Scenario: Lua script handles key initialization and increment atomically
    Tool: Bash (code review + manual verification)
    Preconditions: Lua script is written
    Steps:
      1. Review the Lua script to verify: if key doesn't exist → SET to 1 with TTL, if key exists → INCR and preserve/reset TTL
      2. Verify the script returns the new count value
      3. Verify IPv6 addresses are normalized (colons → dashes) in key construction
    Expected Result: Lua script handles both initialization and increment in a single atomic operation; IPv6 is handled
    Failure Indicators: Script does multiple non-atomic operations, or doesn't handle missing key, or IPv6 breaks key format
    Evidence: .sisyphus/evidence/task-2-lua-script-review.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): add Redis key prefix and Lua atomic increment for IP-only blocking`
  - Files: `crates/router/src/consts.rs`, `crates/router/src/services/card_testing_guard.rs`
  - Pre-commit: `cargo check -p router`

- [ ] 3. Server-side IP extraction with X-Forwarded-For + trusted proxy config

  **What to do**:
  - Add trusted proxy configuration to server settings in `crates/router/src/configs/settings.rs`:
    - Add `trusted_proxies: Vec<String>` field to the relevant settings struct (e.g., `Server` or a new `IpExtraction` section)
    - This will be configured via TOML config file (server-level, not per-merchant)
  - Create a new IP extraction module/function in `crates/router/src/core/card_testing_guard/` (e.g., `ip_extraction.rs`):
    - Function: `extract_client_ip(headers: &HeaderMap, connection_info: &ConnectionInfo, trusted_proxies: &[String]) -> Option<IpAddr>`
    - Logic:
      1. Check if `X-Forwarded-For` header exists
      2. If yes, parse the comma-separated IP list
      3. Walk from right to left: find the first IP that is NOT in the trusted proxies list → this is the client IP
      4. If no X-Forwarded-For or all IPs are trusted, fall back to `connection_info.realip_remote_addr()`
      5. Handle malformed headers gracefully (log warning, fall back to connection IP)
      6. Handle IPv6 addresses in X-Forwarded-For
    - Handle edge cases: empty header, invalid IP, multiple X-Forwarded-For headers, private/internal IPs
  - Wire the trusted proxy config into `SessionState` so it's accessible during request processing
  - This function will be called ONLY by IP-only blocking validation, NOT by existing strategies

  **Must NOT do**:
  - Do NOT change how existing strategies extract IP (they use `browser_info.ip_address`)
  - Do NOT modify Actix middleware chain
  - Do NOT add `Forwarded` header (RFC 7239) support
  - Do NOT make this a global IP extraction change — scoped to card testing guard only
  - Do NOT add per-merchant or per-profile trusted proxy config

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires understanding of HTTP header parsing, IP address handling, and security considerations. Moderate complexity.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 5
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/src/utils/user/dashboard_metadata.rs:295-319` - Existing X-Forwarded-For parsing (takes first IP from comma-separated list). DO NOT follow this pattern exactly — it takes the LEFTMOST IP which is spoofable. Instead, walk from RIGHT to LEFT, skipping trusted proxies.
  - `crates/router/src/routes/payments/helpers.rs:42-63` - Current IP extraction using `req.connection_info().realip_remote_addr()`. Use as fallback.

  **API/Type References** (contracts to implement against):
  - `crates/router/src/configs/settings.rs:89` - `RedisSettings` shows the pattern for adding config sections. Add trusted proxy config following similar patterns.
  - `actix_web::HttpRequest::connection_info()` - API for getting connection info
  - `actix_web::http::header::HeaderMap` - API for reading headers

  **External References**:
  - X-Forwarded-For parsing best practices: Walk right-to-left, skip trusted proxies. The rightmost IP is set by the last trusted proxy; the first untrusted IP from the right is the real client IP.

  **WHY Each Reference Matters**:
  - The dashboard_metadata.rs code shows an existing but INSECURE X-Forwarded-For parsing (takes first IP). We must do the opposite — walk from right, skip trusted proxies.
  - The settings.rs shows where to add the trusted proxy config and how it integrates with TOML parsing.
  - The payments/helpers.rs shows the current IP extraction mechanism we fall back to.

  **Acceptance Criteria**:

  - [ ] `extract_client_ip` function exists in `crates/router/src/core/card_testing_guard/ip_extraction.rs`
  - [ ] Function takes `HeaderMap`, `ConnectionInfo`, and `Vec<String>` (trusted proxies)
  - [ ] Walks X-Forwarded-For from right to left, skipping trusted proxies
  - [ ] Falls back to `connection_info.realip_remote_addr()` when no X-Forwarded-For
  - [ ] Handles malformed headers gracefully (no panic)
  - [ ] Handles IPv6 addresses in X-Forwarded-For
  - [ ] Trusted proxy config added to server settings
  - [ ] `cargo check -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: X-Forwarded-For with trusted proxy extracts correct client IP
    Tool: Bash (unit test)
    Preconditions: Function is implemented
    Steps:
      1. Call extract_client_ip with headers containing "X-Forwarded-For: 203.0.113.50, 70.41.3.18, 10.0.0.1" and trusted_proxies = ["10.0.0.1"]
      2. Assert result is Some(70.41.3.18) — rightmost non-trusted IP
    Expected Result: Returns the first untrusted IP from the right
    Failure Indicators: Returns 203.0.113.50 (leftmost, spoofable) or 10.0.0.1 (trusted proxy)
    Evidence: .sisyphus/evidence/task-3-xff-trusted-proxy.txt

  Scenario: No X-Forwarded-For header falls back to connection info
    Tool: Bash (unit test)
    Preconditions: Function is implemented
    Steps:
      1. Call extract_client_ip with empty headers, connection_info returning "192.168.1.1"
      2. Assert result is Some(192.168.1.1)
    Expected Result: Falls back to connection info IP
    Failure Indicators: Returns None or panics
    Evidence: .sisyphus/evidence/task-3-no-xff-fallback.txt

  Scenario: Malformed X-Forwarded-For header handled gracefully
    Tool: Bash (unit test)
    Preconditions: Function is implemented
    Steps:
      1. Call extract_client_ip with "X-Forwarded-For: not-an-ip, , 10.0.0.1"
      2. Assert no panic, returns connection_info IP as fallback
    Expected Result: Graceful degradation to connection info
    Failure Indicators: Panic or crash
    Evidence: .sisyphus/evidence/task-3-malformed-xff.txt

  Scenario: IPv6 in X-Forwarded-For handled correctly
    Tool: Bash (unit test)
    Preconditions: Function is implemented
    Steps:
      1. Call extract_client_ip with "X-Forwarded-For: 2001:db8::1, 10.0.0.1" and trusted_proxies = ["10.0.0.1"]
      2. Assert result is Some(2001:db8::1)
    Expected Result: IPv6 address parsed and returned correctly
    Failure Indicators: Parse error or None
    Evidence: .sisyphus/evidence/task-3-ipv6-xff.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): add server-side IP extraction with X-Forwarded-For and trusted proxy config`
  - Files: `crates/router/src/core/card_testing_guard/ip_extraction.rs`, `crates/router/src/core/card_testing_guard.rs`, `crates/router/src/configs/settings.rs`
  - Pre-commit: `cargo check -p router`

- [ ] 4. Add IP-only cache key field to CardTestingGuardData

  **What to do**:
  - Add a new optional field to `CardTestingGuardData` in `crates/hyperswitch_domain_models/src/card_testing_guard_data.rs`:
    - `ip_only_blocking_cache_key: Option<String>`
  - This field will hold the Redis cache key for IP-only blocking when the check passes (similar to how existing cache keys are stored for increment on failure)
  - Update any construction sites of `CardTestingGuardData` to include the new field with `None` as default

  **Must NOT do**:
  - Do NOT change existing fields in `CardTestingGuardData`
  - Do NOT remove or rename existing cache key fields

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple struct field addition
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 5, Task 6
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/hyperswitch_domain_models/src/card_testing_guard_data.rs:1-12` - Existing `CardTestingGuardData` struct. Add the new field following the same pattern.

  **API/Type References**:
  - `crates/router/src/core/card_testing_guard/utils.rs:35-70` - Where `CardTestingGuardData` is constructed. Will need to populate the new field in later tasks.

  **WHY Each Reference Matters**:
  - The existing struct shows the exact pattern for cache key storage in CardTestingGuardData
  - The utils.rs shows where the struct is constructed, which will need updating in Task 5/7

  **Acceptance Criteria**:

  - [ ] `ip_only_blocking_cache_key: Option<String>` field added to `CardTestingGuardData`
  - [ ] All construction sites of `CardTestingGuardData` updated to include `None` for the new field
  - [ ] `cargo check -p hyperswitch_domain_models -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CardTestingGuardData compiles with new field
    Tool: Bash
    Preconditions: Code changes are saved
    Steps:
      1. Run `cargo check -p hyperswitch_domain_models -p router`
      2. Grep for `ip_only_blocking_cache_key` in card_testing_guard_data.rs
    Expected Result: Both crates compile; new field is present
    Failure Indicators: Compilation errors
    Evidence: .sisyphus/evidence/task-4-data-struct-compile.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): add IP-only cache key field to CardTestingGuardData`
  - Files: `crates/hyperswitch_domain_models/src/card_testing_guard_data.rs`
  - Pre-commit: `cargo check -p hyperswitch_domain_models -p router`

- [ ] 5. Implement IP-only blocking validation function

  **What to do**:
  - Add a new validation function in `crates/router/src/core/payments/helpers.rs` (after the existing validation functions around lines 1607-1683):
    ```rust
    pub async fn validate_ip_only_blocking_for_business_profile(
        state: &SessionState,
        client_ip: Option<std::net::IpAddr>,
        profile_id: &id_type::ProfileId,
        card_testing_guard_config: &CardTestingGuardConfig,
    ) -> RouterResult<String>
    ```
  - Logic:
    1. Check if `is_ip_only_blocking_enabled` is true — if not, return Ok with empty/placeholder key
    2. If client_ip is None, return Ok (can't block without IP) — log a warning
    3. Normalize the IP for Redis key: replace colons with dashes (for IPv6)
    4. Construct cache key: `IP_ONLY_BLOCKING_{profile_id}_{normalized_ip}`
    5. Call `get_ip_only_blocked_count_from_cache(state, &cache_key)`
    6. If count >= `ip_only_blocking_threshold`, return `Err(ApiErrorResponse::PreconditionFailed { message: "Blocked due to suspicious activity" })`
    7. If count < threshold, return `Ok(cache_key)` — this key will be stored in `CardTestingGuardData` for later increment
  - Use `validate_blocking_threshold` (existing at helpers.rs lines 1665-1682) for the threshold check to maintain consistency
  - This function applies to ALL payment attempts regardless of customer_id presence

  **Must NOT do**:
  - Do NOT modify existing `validate_card_ip_blocking_for_business_profile` or other validation functions
  - Do NOT use `browser_info.ip_address` — use the server-side IP from Task 3's extraction
  - Do NOT block payments when IP is unavailable (graceful degradation)
  - Do NOT create a separate error message — reuse "Blocked due to suspicious activity"

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Core business logic with security implications. Must get the validation flow exactly right.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Tasks 1, 2, 3, 4
  - **Parallel Group**: Wave 2 (with Tasks 6, 7)
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 1, 2, 3, 4

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/src/core/payments/helpers.rs:1607-1622` - `validate_card_ip_blocking_for_business_profile`. Follow this exact pattern for the new function — same signature style, same threshold check, same error type.
  - `crates/router/src/core/payments/helpers.rs:1665-1682` - `validate_blocking_threshold`. Reuse this for the actual threshold comparison.
  - `crates/router/src/core/payments/helpers.rs:1625-1644` - `validate_guest_user_card_blocking_for_business_profile`. Shows how to handle optional identifiers (graceful skip when identifier is absent).

  **API/Type References**:
  - `crates/router/src/services/card_testing_guard.rs` - The new `get_ip_only_blocked_count_from_cache` function from Task 2
  - `crates/diesel_models/src/business_profile.rs:825-854` - `CardTestingGuardConfig` with new `is_ip_only_blocking_enabled` and `ip_only_blocking_threshold` fields from Task 1
  - `crates/router/src/consts.rs:88-92` - `IP_ONLY_BLOCKING_CACHE_KEY_PREFIX` from Task 2

  **WHY Each Reference Matters**:
  - The existing validation functions show the exact error handling, return type, and control flow pattern to follow
  - `validate_guest_user_card_blocking` shows how to handle optional data (skip when absent) — same pattern for missing IP
  - `validate_blocking_threshold` is the shared threshold check — reuse it to maintain consistency

  **Acceptance Criteria**:

  - [ ] `validate_ip_only_blocking_for_business_profile` function exists in `helpers.rs`
  - [ ] Function checks `is_ip_only_blocking_enabled` flag and skips if disabled
  - [ ] Function gracefully handles missing IP (returns Ok, doesn't block)
  - [ ] Function constructs Redis key with profile_id and normalized IP
  - [ ] Function uses `validate_blocking_threshold` for the actual threshold check
  - [ ] Function returns `PreconditionFailed` error when threshold exceeded
  - [ ] `cargo check -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: IP-only blocking triggers when threshold exceeded
    Tool: Bash (cargo test)
    Preconditions: Redis mock is set up with count >= threshold for a given IP
    Steps:
      1. Create a test that sets Redis mock to return count=10 for IP "203.0.113.50" with profile_id "prof_123"
      2. Call validate_ip_only_blocking_for_business_profile with ip_only_blocking_enabled=true, threshold=10
      3. Assert result is Err(PreconditionFailed { message: "Blocked due to suspicious activity" })
    Expected Result: Returns PreconditionFailed error
    Failure Indicators: Returns Ok or different error type
    Evidence: .sisyphus/evidence/task-5-blocking-triggers.txt

  Scenario: IP-only blocking does NOT trigger when disabled
    Tool: Bash (cargo test)
    Preconditions: Redis has count exceeding threshold
    Steps:
      1. Call validate_ip_only_blocking_for_business_profile with ip_only_blocking_enabled=false
      2. Assert result is Ok (no blocking even though count exceeds threshold)
    Expected Result: Returns Ok without checking Redis
    Failure Indicators: Returns Err or checks Redis when disabled
    Evidence: .sisyphus/evidence/task-5-blocking-disabled.txt

  Scenario: Missing IP does not block payment (graceful degradation)
    Tool: Bash (cargo test)
    Preconditions: None
    Steps:
      1. Call validate_ip_only_blocking_for_business_profile with client_ip=None
      2. Assert result is Ok (payment proceeds without IP-only check)
    Expected Result: Returns Ok without blocking
    Failure Indicators: Returns Err or panics
    Evidence: .sisyphus/evidence/task-5-missing-ip-graceful.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): implement IP-only blocking validation`
  - Files: `crates/router/src/core/payments/helpers.rs`
  - Pre-commit: `cargo check -p router`

- [ ] 6. Increment IP-only counter on payment failure

  **What to do**:
  - Modify the payment failure handler in `crates/router/src/core/payments/operations/payment_response.rs` (lines 2881-2887) to also increment the IP-only counter when a payment fails
  - Currently, the code increments the existing card testing guard counters on `AttemptStatus::Failure`
  - Add a call to `increment_ip_only_blocked_count_in_cache` (from Task 2) using the `ip_only_blocking_cache_key` from `CardTestingGuardData`
  - Only increment if `ip_only_blocking_cache_key` is `Some` (meaning the IP-only check was performed and passed)
  - The increment uses the atomic Lua script from Task 2

  **Must NOT do**:
  - Do NOT change how existing counters are incremented (they still use the non-atomic GET→SET)
  - Do NOT increment on payment success or other statuses — only on `Failure`
  - Do NOT increment if the payment was already blocked by the guard (the key wouldn't have been stored)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Must correctly integrate into the payment failure flow without breaking existing behavior
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Tasks 2, 4
  - **Parallel Group**: Wave 2 (with Tasks 5, 7)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 2, 4

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/src/core/payments/operations/payment_response.rs:2881-2887` - Existing increment logic on payment failure. Add the new increment call in the same block, following the same pattern.

  **API/Type References**:
  - `crates/router/src/services/card_testing_guard.rs` - `increment_ip_only_blocked_count_in_cache` function from Task 2
  - `crates/hyperswitch_domain_models/src/card_testing_guard_data.rs` - `CardTestingGuardData` with `ip_only_blocking_cache_key` from Task 4

  **WHY Each Reference Matters**:
  - The existing increment code shows exactly where and how to add the new counter increment
  - The CardTestingGuardData field tells us whether the IP-only check was performed (key is Some) or not (key is None)

  **Acceptance Criteria**:

  - [ ] `increment_ip_only_blocked_count_in_cache` is called on `AttemptStatus::Failure` when `ip_only_blocking_cache_key` is `Some`
  - [ ] Existing counter increments are untouched
  - [ ] No increment happens on payment success or other statuses
  - [ ] `cargo check -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: IP-only counter increments on payment failure
    Tool: Bash (code review)
    Preconditions: Code changes are saved
    Steps:
      1. Verify that `increment_ip_only_blocked_count_in_cache` is called in the `AttemptStatus::Failure` branch
      2. Verify it's only called when `ip_only_blocking_cache_key.is_some()`
      3. Verify existing `increment_blocked_count_in_cache` calls are still present and unchanged
    Expected Result: New increment call added alongside existing ones, guarded by Option check
    Failure Indicators: Missing increment, unconditional increment, or removed existing increments
    Evidence: .sisyphus/evidence/task-6-increment-on-failure.txt

  Scenario: IP-only counter does NOT increment on payment success
    Tool: Bash (code review)
    Preconditions: Code changes are saved
    Steps:
      1. Verify the increment is ONLY inside the `AttemptStatus::Failure` branch
      2. Verify no increment happens in other status branches
    Expected Result: Increment only on Failure status
    Failure Indicators: Increment in wrong status branch
    Evidence: .sisyphus/evidence/task-6-no-increment-success.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): increment IP-only counter on payment failure`
  - Files: `crates/router/src/core/payments/operations/payment_response.rs`
  - Pre-commit: `cargo check -p router`

- [ ] 7. Wire IP-only validation into card_testing_guard_checks

  **What to do**:
  - Modify `validate_card_testing_guard_checks` in `crates/router/src/core/card_testing_guard/utils.rs` to:
    1. Extract the server-side client IP using the function from Task 3 (`extract_client_ip`)
    2. Call `validate_ip_only_blocking_for_business_profile` with the extracted IP, profile_id, and config
    3. Store the returned cache key in `CardTestingGuardData.ip_only_blocking_cache_key`
  - The function should be called AFTER the existing validation checks (card_ip_blocking, guest_user_card_blocking, customer_id_blocking) — the IP-only check is additive
  - Pass the `HttpRequest` or `HeaderMap` + `ConnectionInfo` through the call chain so `extract_client_ip` can access them. This may require:
    - Adding parameters to `validate_card_testing_guard_checks`
    - Updating the call sites in `payments.rs` (v1 eligibility) and `payment_confirm.rs` (v2 confirm) to pass request info
  - Ensure the `CardTestingGuardData` returned includes both existing cache keys AND the new `ip_only_blocking_cache_key`

  **Must NOT do**:
  - Do NOT change the order of existing validation checks
  - Do NOT make IP-only blocking depend on other checks passing or failing
  - Do NOT remove or alter existing validation logic
  - Do NOT pass `browser_info.ip_address` — use the server-side IP extraction from Task 3

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Integration work that touches the main validation flow. Must be careful not to break existing behavior.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Task 5
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Tasks 8, 9
  - **Blocked By**: Task 5

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/src/core/card_testing_guard/utils.rs:35-70` - `validate_card_testing_guard_checks` function. This is the main entry point to modify. Understand how it currently calls the 3 validation functions and constructs `CardTestingGuardData`.
  - `crates/router/src/core/payments.rs:12316-12348` - v1 eligibility check call site. Will need to pass `HttpRequest` info.
  - `crates/router/src/core/payments/operations/payment_confirm.rs:976-984` - v2 payment confirm call site. Will need to pass `HttpRequest` info.

  **API/Type References**:
  - `crates/router/src/core/card_testing_guard/ip_extraction.rs` - `extract_client_ip` from Task 3
  - `crates/router/src/core/payments/helpers.rs` - `validate_ip_only_blocking_for_business_profile` from Task 5
  - `crates/hyperswitch_domain_models/src/card_testing_guard_data.rs` - `CardTestingGuardData` with `ip_only_blocking_cache_key` from Task 4
  - `crates/router/src/configs/settings.rs` - Trusted proxy config from Task 3, accessible via `SessionState`

  **WHY Each Reference Matters**:
  - The utils.rs function is the exact place to add the new validation call — it already orchestrates the existing checks
  - The v1 and v2 call sites show where the request info is available and how to thread it through
  - The IP extraction function provides the server-side IP that IP-only blocking must use

  **Acceptance Criteria**:

  - [ ] `validate_card_testing_guard_checks` calls `validate_ip_only_blocking_for_business_profile`
  - [ ] Server-side IP is extracted using `extract_client_ip` (not browser_info.ip_address)
  - [ ] Result is stored in `CardTestingGuardData.ip_only_blocking_cache_key`
  - [ ] Existing validation checks are unchanged
  - [ ] Both v1 (eligibility) and v2 (confirm) call sites pass required request info
  - [ ] `cargo check -p router` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: IP-only check is called alongside existing checks
    Tool: Bash (code review + cargo check)
    Preconditions: Code changes are saved
    Steps:
      1. Verify `validate_card_testing_guard_checks` calls `validate_ip_only_blocking_for_business_profile`
      2. Verify it's called regardless of whether other checks pass or fail
      3. Verify `CardTestingGuardData` includes `ip_only_blocking_cache_key`
      4. Run `cargo check -p router`
    Expected Result: IP-only check is integrated; existing checks unchanged; compilation passes
    Failure Indicators: Missing integration call, existing check behavior changed, or compilation error
    Evidence: .sisyphus/evidence/task-7-wired-integration.txt

  Scenario: v1 and v2 call sites provide request info for IP extraction
    Tool: Bash (code review)
    Preconditions: Code changes are saved
    Steps:
      1. Verify `payments.rs` eligibility check passes request headers/connection info
      2. Verify `payment_confirm.rs` confirm check passes request headers/connection info
      3. Verify `extract_client_ip` is called with the correct parameters
    Expected Result: Both call sites thread request info through to the guard checks
    Failure Indicators: Missing parameter passing or incorrect IP extraction call
    Evidence: .sisyphus/evidence/task-7-call-sites.txt
  ```

  **Commit**: YES
  - Message: `feat(card-testing-guard): wire IP-only validation into guard checks`
  - Files: `crates/router/src/core/card_testing_guard/utils.rs`, `crates/router/src/core/payments.rs`, `crates/router/src/core/payments/operations/payment_confirm.rs`
  - Pre-commit: `cargo check -p router`

- [ ] 8. Unit tests for IP-only blocking logic

  **What to do**:
  - Create a test module in `crates/router/src/core/card_testing_guard/utils.rs` (or a separate test file) with `#[cfg(test)]`:
    - Test `validate_ip_only_blocking_for_business_profile`:
      - Blocking triggers when count >= threshold
      - Blocking does NOT trigger when count < threshold
      - Blocking does NOT trigger when disabled
      - Graceful handling when IP is None
      - Redis error returns InternalServerError
    - Test `extract_client_ip`:
      - X-Forwarded-For with trusted proxy returns correct IP
      - No X-Forwarded-For falls back to connection info
      - Malformed header falls back gracefully
      - IPv6 addresses handled correctly
      - Multiple hops in X-Forwarded-For with multiple trusted proxies
    - Test Redis key construction:
      - IPv6 addresses have colons replaced with dashes
      - Key format is `IP_ONLY_BLOCKING_{profile_id}_{normalized_ip}`
    - Test atomic increment:
      - Lua script increments correctly
      - Lua script initializes key when it doesn't exist
      - Lua script sets TTL correctly
  - Mock Redis using the project's test utilities or a simple mock
  - Follow existing test patterns from `crates/router/tests/`

  **Must NOT do**:
  - Do NOT skip testing edge cases (missing IP, IPv6, malformed headers)
  - Do NOT write integration tests here — those are in Task 9
  - Do NOT use live Redis for unit tests — mock it

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Comprehensive test coverage requires understanding the full validation flow and all edge cases
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Tasks 5, 7
  - **Parallel Group**: Wave 3 (with Tasks 9, 10)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 5, 7

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/router/tests/connectors/stripe.rs` - Example test using `#[actix_web::test]`
  - `crates/common_utils/tests/percentage.rs` - Example unit test with assertions and error matching

  **Test References**:
  - `crates/redis_interface/src/test.rs:1795-1827` - Lua script test pattern

  **WHY Each Reference Matters**:
  - The test patterns show the assertion style and test organization to follow
  - The Lua script test shows how to test Redis Lua scripts

  **Acceptance Criteria**:

  - [ ] Test module exists in card_testing_guard with `#[cfg(test)]`
  - [ ] Tests cover: blocking triggers, blocking disabled, missing IP, threshold check, IPv6 key format
  - [ ] Tests cover: X-Forwarded-For parsing with trusted proxies, fallback, malformed headers, IPv6
  - [ ] Tests cover: atomic increment Lua script behavior
  - [ ] `cargo test -p router card_testing_guard` passes with 0 failures

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All unit tests pass
    Tool: Bash
    Preconditions: Tests are written
    Steps:
      1. Run `cargo test -p router card_testing_guard -- --nocapture`
      2. Verify all tests pass
      3. Count the number of test cases — expect at least 10
    Expected Result: All tests pass; minimum 10 test cases covering all edge cases
    Failure Indicators: Any test failure or fewer than 10 test cases
    Evidence: .sisyphus/evidence/task-8-unit-tests-pass.txt

  Scenario: Test coverage includes all edge cases
    Tool: Bash (grep)
    Preconditions: Tests are written
    Steps:
      1. Grep test file for: "disabled", "None", "IPv6", "threshold", "X-Forwarded-For", "malformed", "trusted_proxy"
      2. Verify each keyword appears in at least one test
    Expected Result: All edge case keywords covered in tests
    Failure Indicators: Missing keyword coverage
    Evidence: .sisyphus/evidence/task-8-edge-case-coverage.txt
  ```

  **Commit**: YES
  - Message: `test(card-testing-guard): add unit tests for IP-only blocking`
  - Files: `crates/router/src/core/card_testing_guard/utils.rs` (or new test file)
  - Pre-commit: `cargo test -p router card_testing_guard`

- [ ] 9. Update Cypress integration tests

  **What to do**:
  - Update the existing Cypress test file `cypress-tests/cypress/e2e/spec/Payment/52-CardTestingGuard.cy.js` to add IP-only blocking scenarios:
    1. **IP-only blocking triggers**: Enable `ip_only_blocking` with threshold=3 → make 3 failed payments from same IP with DIFFERENT card numbers → 4th payment is blocked
    2. **IP-only blocking independent of card_ip_blocking**: Disable `card_ip_blocking` → Enable `ip_only_blocking` → verify IP-only blocking still works
    3. **IP-only blocking disabled**: Disable `ip_only_blocking` → exceed threshold → verify payments are NOT blocked
    4. **IP-only blocking with customer_id present**: Enable `ip_only_blocking` → make failed payments with customer_id from same IP → verify blocking triggers (not just guest checkout)
    5. **Regression**: Existing card_ip_blocking scenarios still pass
  - Follow the existing test pattern in the file (config update → payments → assertions)

  **Must NOT do**:
  - Do NOT modify existing test scenarios (only add new ones)
  - Do NOT add test infrastructure changes
  - Do NOT test X-Forwarded-For in Cypress (that's a server-side concern for unit tests)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Cypress tests require understanding of the existing test patterns and the business logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Task 7
  - **Parallel Group**: Wave 3 (with Tasks 8, 10)
  - **Blocks**: Task 10
  - **Blocked By**: Task 7

  **References**:

  **Pattern References** (existing code to follow):
  - `cypress-tests/cypress/e2e/spec/Payment/52-CardTestingGuard.cy.js` - Existing card testing guard Cypress tests. Add new test scenarios following the same pattern (describe/it blocks, API calls, assertions).

  **WHY Each Reference Matters**:
  - The existing Cypress test shows the exact API call patterns, assertion style, and test data setup needed

  **Acceptance Criteria**:

  - [ ] New Cypress test scenarios added for IP-only blocking
  - [ ] Scenarios cover: threshold exceeded, disabled, independent from card_ip_blocking, with customer_id
  - [ ] Existing test scenarios untouched
  - [ ] Regression scenario confirms existing card_ip_blocking still works

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: New Cypress test scenarios are comprehensive
    Tool: Bash (grep)
    Preconditions: Cypress tests are updated
    Steps:
      1. Grep for "ip_only_blocking" in the Cypress test file
      2. Verify at least 4 new test scenarios exist
      3. Verify no existing test scenarios were modified
    Expected Result: At least 4 new IP-only test scenarios; existing scenarios untouched
    Failure Indicators: Missing scenarios or modified existing tests
    Evidence: .sisyphus/evidence/task-9-cypress-scenarios.txt
  ```

  **Commit**: YES
  - Message: `test(card-testing-guard): update Cypress integration tests for IP-only blocking`
  - Files: `cypress-tests/cypress/e2e/spec/Payment/52-CardTestingGuard.cy.js`
  - Pre-commit: None (Cypress tests require running server)

- [ ] 10. End-to-end QA verification

  **What to do**:
  - Verify the complete IP-only blocking feature works end-to-end:
    1. Start the Hyperswitch server with trusted proxy configuration
    2. Configure a business profile with `ip_only_blocking_enabled: true` and `ip_only_blocking_threshold: 3`
    3. Make 3 failed card payments from the same IP with different card numbers
    4. Verify 4th payment attempt returns `PreconditionFailed` with "Blocked due to suspicious activity"
    5. Verify existing card_ip_blocking, guest_user_card_blocking, customer_id_blocking still work
    6. Test with X-Forwarded-For header
    7. Test backward compatibility (profile without new fields)
  - Verify all unit tests pass
  - Verify cargo clippy passes

  **Must NOT do**:
  - Do NOT skip any QA scenario
  - Do NOT mark complete without evidence for each scenario

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Comprehensive end-to-end verification requires running the system and testing all scenarios
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on Tasks 8, 9
  - **Parallel Group**: Wave 3 (standalone)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 8, 9

  **References**:

  **Pattern References**:
  - All previous task references for verification steps

  **Acceptance Criteria**:

  - [ ] All `cargo test -p router card_testing_guard` tests pass
  - [ ] `cargo clippy -p router` passes with no warnings
  - [ ] IP-only blocking triggers after threshold exceeded (verified via API call)
  - [ ] Existing strategies unaffected (regression verified)
  - [ ] Evidence files captured for each scenario

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full end-to-end IP-only blocking works
    Tool: Bash (curl + cargo test)
    Preconditions: Server is running with config
    Steps:
      1. Run `cargo test -p router card_testing_guard` → verify all pass
      2. Run `cargo clippy -p router` → verify no warnings
      3. Configure business profile with ip_only_blocking_enabled=true, threshold=3
      4. Make 3 failed payments from same IP with different cards
      5. Make 4th payment → verify PreconditionFailed response
      6. Disable ip_only_blocking → make payments → verify no blocking
      7. Enable card_ip_blocking → verify existing strategy still works
    Expected Result: IP-only blocking triggers at threshold; existing strategies unaffected
    Failure Indicators: Blocking doesn't trigger, existing strategies broken, or test failures
    Evidence: .sisyphus/evidence/task-10-e2e-verification.txt
  ```

  **Commit**: NO (verification task, no code changes)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `cargo clippy` + `cargo test`. Review all changed files for: `as any`, empty catches, `println!` in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify no changes to existing strategy behavior.
  Output: `Build [PASS/FAIL] | Clippy [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration. Test edge cases: missing IP, IPv6, invalid X-Forwarded-For, backward compatibility. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Task 1**: `feat(card-testing-guard): add ip_only_blocking config fields` - config files
- **Task 2**: `feat(card-testing-guard): add Redis key prefix and Lua atomic increment` - consts + redis service
- **Task 3**: `feat(card-testing-guard): add server-side IP extraction with X-Forwarded-For` - IP extraction + trusted proxy config
- **Task 4**: `feat(card-testing-guard): add IP-only cache key field to CardTestingGuardData` - domain model
- **Task 5**: `feat(card-testing-guard): implement IP-only blocking validation` - validation logic
- **Task 6**: `feat(card-testing-guard): increment IP-only counter on payment failure` - response handler
- **Task 7**: `feat(card-testing-guard): wire IP-only validation into guard checks` - integration
- **Task 8**: `test(card-testing-guard): add unit tests for IP-only blocking` - test files
- **Task 9**: `test(card-testing-guard): update Cypress integration tests` - cypress files

---

## Success Criteria

### Verification Commands
```bash
cargo test -p router card_testing_guard  # Expected: all tests pass
cargo clippy -p router  # Expected: no warnings
just clippy  # Expected: no warnings
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Existing card_ip_blocking behavior unchanged
- [ ] IP-only blocking works independently
- [ ] X-Forwarded-For parsing with trusted proxies works
- [ ] Backward compatibility verified
