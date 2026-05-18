# Refactor Apple Pay Session Response to Opaque JSON

## TL;DR

> **Quick Summary**: Replace the concrete `NoThirdPartySdkSessionResponse` struct with `serde_json::Value` in the `ApplePaySessionResponse::NoThirdPartySdk` enum variant, per Apple's documentation that the merchant session response should be treated as opaque (format/fields liable to change without notice).
> 
> **Deliverables**:
> - `ApplePaySessionResponse::NoThirdPartySdk` variant wraps `serde_json::Value` instead of `NoThirdPartySdkSessionResponse`
> - `NoThirdPartySdkSessionResponse` struct definition removed
> - All parsing sites updated to parse as `serde_json::Value`
> - `Eq`/`PartialEq` removed from cascading types
> - OpenAPI specs regenerated
> - Zero remaining references to `NoThirdPartySdkSessionResponse`
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO - sequential (type system cascade requires ordered changes)
> **Critical Path**: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6

---

## Context

### Original Request
In `crates/router/src/core/payments/flows/session_flow.rs`, the `create_applepay_session_token` function parses the Apple Pay session token response into `NoThirdPartySdkSessionResponse`. However, Apple's documentation states: "The response for the Apple Pay Merchant Session should be treated as opaque, so you shouldn't need to inspect or type check the object. The format, layout and field names of the response is liable to change without notice." So instead of a concrete struct, the `ApplePaySessionResponse::NoThirdPartySdk` enum should contain generic JSON (`serde_json::Value`), not a parsed struct.

### Interview Summary
**Key Discussions**:
- The refactor is specifically about the `NoThirdPartySdk` variant only; `ThirdPartySdk` and `NoSessionResponse` variants are unaffected
- The `#[serde(untagged)]` on the enum means JSON passes through transparently — no variant discriminator in output
- `serde_json::Value` is already widely used in api_models (83+ occurrences)
- Zero dedicated tests exist for these types, so no test breakage risk

**Research Findings**:
- `serde_json::Value` does NOT implement `Eq`/`PartialEq` — must remove these derives from 3 cascading types
- `serde_json::Value` auto-resolves to `smithy.api#Document` in SmithyModel derive (no `#[smithy(value_type)]` needed)
- `#[schema(value_type = serde_json::Value)]` is only used on struct fields, NEVER on enum variants — the type's inherent `ToSchema` impl is sufficient
- The gRPC transformer only handles `ThirdPartySdk` variant — no change needed

### Metis Review
**Identified Gaps** (addressed):
- **Eq cascade**: Must remove `Eq`/`PartialEq` from `ApplePaySessionResponse`, `ApplepaySessionTokenResponse`, AND `SessionToken` — not just the enum
- **Smithy attribute**: Must REMOVE `#[smithy(value_type = "NoThirdPartySdkSessionResponse")]` entirely from the variant, not replace it — `serde_json::Value` auto-resolves to `smithy.api#Document`
- **Schema attribute**: Do NOT add `#[schema(value_type = serde_json::Value)]` to the enum variant — untested pattern and unnecessary
- **OpenAPI regeneration**: Checked-in JSON specs must be regenerated after struct removal
- **Bluesnap import cleanup**: The `NoThirdPartySdkSessionResponse` import in bluesnap transformers must be removed to avoid dead code warnings

---

## Work Objectives

### Core Objective
Replace `NoThirdPartySdkSessionResponse` concrete struct with `serde_json::Value` in the `ApplePaySessionResponse::NoThirdPartySdk` enum variant, making the Apple Pay session response opaque per Apple's documentation.

### Concrete Deliverables
- Modified `ApplePaySessionResponse` enum in `crates/api_models/src/payments.rs`
- Removed `NoThirdPartySdkSessionResponse` struct definition
- Updated parsing in `crates/router/src/core/payments/flows/session_flow.rs`
- Updated parsing in `crates/hyperswitch_connectors/src/connectors/bluesnap/transformers.rs`
- Updated `crates/openapi/src/openapi.rs` and `crates/openapi/src/openapi_v2.rs`
- Regenerated `api-reference/v1/openapi_spec_v1.json` and `api-reference/v2/openapi_spec_v2.json`

### Definition of Done
- [ ] `cargo check --all-targets` passes with zero errors
- [ ] `grep -r "NoThirdPartySdkSessionResponse" crates/ api-reference/` returns zero matches
- [ ] Regenerated OpenAPI specs contain no `$ref` to `NoThirdPartySdkSessionResponse`
- [ ] `Eq`/`PartialEq` removed from all three cascading types

### Must Have
- `ApplePaySessionResponse::NoThirdPartySdk(serde_json::Value)` — no `#[schema]` or `#[smithy]` attribute on the variant
- Complete removal of `NoThirdPartySdkSessionResponse` struct definition
- `Eq`/`PartialEq` removed from `ApplePaySessionResponse`, `ApplepaySessionTokenResponse`, and `SessionToken`
- All compilation errors resolved across all crates
- OpenAPI specs regenerated

### Must NOT Have (Guardrails)
- Do NOT add `#[schema(value_type = serde_json::Value)]` on the enum variant — untested pattern, unnecessary
- Do NOT add `#[smithy(value_type = "...")]` on the variant — `serde_json::Value` auto-resolves to `smithy.api#Document`
- Do NOT modify `ThirdPartySdk` or `NoSessionResponse` variants
- Do NOT modify the gRPC `ForeignTryFrom` impl in `unified_connector_service/transformers.rs`
- Do NOT change the `parse_struct` function signature — only change the type annotation `T`
- Do NOT add tests as part of this task
- Do NOT touch downstream SDK repos (web/mobile) — wire JSON remains identical
- Do NOT add a `From<serde_json::Value>` for gRPC conversion

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: None (no existing tests for these types; not adding new ones)
- **Framework**: N/A
- **Compilation testing**: User will verify manually after execution

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Library/Module**: Use Bash (`cargo check`, `grep`) — Build verification and reference search
- **Note**: User has requested to skip automated compilation testing — they will verify `cargo check --all-targets` manually after execution

---

## Execution Strategy

### Sequential Execution (type system cascade requires ordering)

```
Step 1: Remove Eq/PartialEq from ApplePaySessionResponse enum + change variant type
Step 2: Remove NoThirdPartySdkSessionResponse struct definition
Step 3: Remove Eq/PartialEq from ApplepaySessionTokenResponse
Step 4: Remove Eq/PartialEq from SessionToken
Step 5: Update session_flow.rs parsing (type annotation change)
Step 6: Update bluesnap/transformers.rs parsing (type annotation + import change)
Step 7: Update OpenAPI generator files (remove struct registration)
Step 8: Regenerate OpenAPI spec JSON files
Step 9: Final verification sweep

Critical Path: Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6 → Step 7 → Step 8 → Step 9
Sequential (type system dependency chain)
```

### Dependency Matrix

- **1**: - → 2,3,4
- **2**: 1 → 5,6,7
- **3**: 1 → 4
- **4**: 3 → 5,6
- **5**: 2,4 → 9
- **6**: 2,4 → 9
- **7**: 2 → 8
- **8**: 7 → 9
- **9**: 5,6,8 -

### Agent Dispatch Summary

- **All tasks**: `quick` — single-type changes with compile-guided verification

---

## TODOs

- [x] 1. Change `ApplePaySessionResponse::NoThirdPartySdk` variant to wrap `serde_json::Value` and remove `Eq`/`PartialEq` derives

  **What to do**:
  - In `crates/api_models/src/payments.rs` (around line 10721-10737):
    - Remove `Eq, PartialEq` from the derive list of `ApplePaySessionResponse` (keep `Debug, Clone, serde::Serialize, serde::Deserialize, ToSchema, SmithyModel`)
    - Change `NoThirdPartySdk(NoThirdPartySdkSessionResponse)` to `NoThirdPartySdk(serde_json::Value)`
    - **Remove** the `#[smithy(value_type = "NoThirdPartySdkSessionResponse")]` attribute from the `NoThirdPartySdk` variant entirely — do NOT replace it with another `value_type`; `serde_json::Value` auto-resolves to `smithy.api#Document` in the SmithyModel derive
    - Do NOT add `#[schema(value_type = serde_json::Value)]` to the variant — the type's inherent `ToSchema` impl is sufficient and this pattern is untested on enum variants
  - Run `cargo check -p api_models` to verify compilation

  **Must NOT do**:
  - Do NOT modify `ThirdPartySdk` or `NoSessionResponse` variants
  - Do NOT add `#[schema]` or `#[smithy]` attributes to the `NoThirdPartySdk` variant
  - Do NOT remove `serde::Serialize`, `serde::Deserialize`, `ToSchema`, or `SmithyModel` derives

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-type change with compile-guided verification
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 1)
  - **Blocks**: Tasks 2, 3, 4
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `crates/api_models/src/payments.rs:10721-10737` — Current `ApplePaySessionResponse` enum definition with derives and variant attributes
  - `crates/api_models/src/authentication.rs:295` — Example of `#[schema(value_type = serde_json::Value)]` on a struct field (for reference, do NOT copy this pattern to enum variant)
  - `crates/api_models/src/payments.rs:10724` — `#[serde(untagged)]` attribute on the enum — must be preserved

  **API/Type References** (contracts to implement against):
  - `crates/api_models/src/payments.rs:10732-10733` — The specific variant line: `#[smithy(value_type = "NoThirdPartySdkSessionResponse")] NoThirdPartySdk(NoThirdPartySdkSessionResponse)` — this is what needs to change
  - `crates/api_models/src/payments.rs:10722` — Derive list: `Debug, Clone, Eq, PartialEq, serde::Serialize, serde::Deserialize, ToSchema, SmithyModel` — remove `Eq, PartialEq`

  **WHY Each Reference Matters**:
  - The enum definition is the single source of truth for the type change
  - The authentication.rs reference shows `serde_json::Value` is already used with `ToSchema` in this crate
  - The `#[serde(untagged)]` must be preserved — it ensures JSON passes through transparently

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after enum variant change
    Tool: Bash
    Preconditions: Working directory is hyperswitch root
    Steps:
      1. Run `cargo check -p api_models 2>&1`
      2. Check exit code is 0
      3. If non-zero, examine errors for Eq/PartialEq cascade (expected — will be fixed in tasks 3-4)
    Expected Result: Compilation either succeeds or only has Eq-related errors in dependent types (ApplepaySessionTokenResponse, SessionToken)
    Failure Indicators: Errors unrelated to Eq/PartialEq cascade (e.g., trait bound errors on serde_json::Value)
    Evidence: .sisyphus/evidence/task-1-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 2. Remove `NoThirdPartySdkSessionResponse` struct definition

  **What to do**:
  - In `crates/api_models/src/payments.rs` (around lines 10739-10778):
    - Delete the entire `NoThirdPartySdkSessionResponse` struct definition including:
      - The `#[derive(...)]` block
      - The `#[serde(rename_all(deserialize = "camelCase"))]` attribute
      - The `#[smithy(namespace = "com.hyperswitch.smithy.types")]` attribute
      - All struct fields (epoch_timestamp, expires_at, merchant_session_identifier, nonce, merchant_identifier, domain_name, display_name, signature, operational_analytics_identifier, retries, psp_id)
  - Run `cargo check -p api_models` to see remaining errors (expected: references in other files will break)

  **Must NOT do**:
  - Do NOT remove `ThirdPartySdkSessionResponse` struct (lines 10780-10787)
  - Do NOT remove any other struct in the file

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple struct deletion
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 2, after Task 1)
  - **Blocks**: Tasks 5, 6, 7
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `crates/api_models/src/payments.rs:10739-10778` — The `NoThirdPartySdkSessionResponse` struct definition to remove
  - `crates/api_models/src/payments.rs:10780-10787` — `ThirdPartySdkSessionResponse` struct — do NOT remove this

  **WHY Each Reference Matters**:
  - The struct definition is what needs to be completely removed
  - The ThirdPartySdkSessionResponse reference is the boundary — don't delete past line 10778

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Struct definition fully removed
    Tool: Bash
    Preconditions: Task 1 completed
    Steps:
      1. Run `grep -n "NoThirdPartySdkSessionResponse" crates/api_models/src/payments.rs`
      2. Verify zero matches in the file
    Expected Result: Zero matches — struct definition and all references within api_models are gone
    Failure Indicators: Any remaining reference to NoThirdPartySdkSessionResponse in payments.rs
    Evidence: .sisyphus/evidence/task-2-struct-removed.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 3. Remove `Eq`/`PartialEq` from `ApplepaySessionTokenResponse` derive

  **What to do**:
  - In `crates/api_models/src/payments.rs` (around line 10656):
    - Find the `ApplepaySessionTokenResponse` struct derive list
    - Remove `Eq, PartialEq` from the derive list
    - Keep all other derives (`Debug, Clone, serde::Serialize, serde::Deserialize, ToSchema, SmithyModel`, etc.)
  - Run `cargo check -p api_models` to check for cascade errors

  **Must NOT do**:
  - Do NOT remove other derives from `ApplepaySessionTokenResponse`
  - Do NOT change any fields of `ApplepaySessionTokenResponse`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single derive removal
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 3, after Task 1)
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `crates/api_models/src/payments.rs:10656` — `ApplepaySessionTokenResponse` derive list (contains `session_token_data: Option<ApplePaySessionResponse>` which transitively loses `Eq`)

  **WHY Each Reference Matters**:
  - This type contains `Option<ApplePaySessionResponse>`, so it can no longer derive `Eq` after the inner type drops it

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after Eq removal from ApplepaySessionTokenResponse
    Tool: Bash
    Preconditions: Tasks 1 and 2 completed
    Steps:
      1. Run `cargo check -p api_models 2>&1`
      2. Check for Eq-related errors in SessionToken (expected cascade)
    Expected Result: No errors related to ApplepaySessionTokenResponse. May have errors in SessionToken (fixed in task 4).
    Failure Indicators: Errors unrelated to SessionToken Eq cascade
    Evidence: .sisyphus/evidence/task-3-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 4. Remove `Eq`/`PartialEq` from `SessionToken` derive

  **What to do**:
  - In `crates/api_models/src/payments.rs` (around line 10312):
    - Find the `SessionToken` enum derive list
    - Remove `Eq, PartialEq` from the derive list
    - Keep all other derives
  - Run `cargo check -p api_models` — should now compile cleanly for api_models crate

  **Must NOT do**:
  - Do NOT remove other derives from `SessionToken`
  - Do NOT change any variants of `SessionToken`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single derive removal
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 4, after Task 3)
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: Task 3

  **References**:

  **Pattern References**:
  - `crates/api_models/src/payments.rs:10312` — `SessionToken` derive list (contains `ApplePay(Box<ApplepaySessionTokenResponse>)` which transitively loses `Eq`)

  **WHY Each Reference Matters**:
  - This type contains `ApplePay(Box<ApplepaySessionTokenResponse>)`, so it can no longer derive `Eq` after the inner type drops it

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after Eq removal from SessionToken
    Tool: Bash
    Preconditions: Tasks 1-3 completed
    Steps:
      1. Run `cargo check -p api_models 2>&1`
      2. Verify zero errors in api_models crate
    Expected Result: `cargo check -p api_models` succeeds with zero errors
    Failure Indicators: Any compilation errors in api_models
    Evidence: .sisyphus/evidence/task-4-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 5. Update `session_flow.rs` — change parsing type annotation from `NoThirdPartySdkSessionResponse` to `serde_json::Value`

  **What to do**:
  - In `crates/router/src/core/payments/flows/session_flow.rs`:
    - Line ~577: Change `payment_types::NoThirdPartySdkSessionResponse` to `serde_json::Value` in the type annotation
    - Line ~579: The `parse_struct("NoThirdPartySdkSessionResponse")` call should remain — just change the generic type `T`. The string argument is only used for error messages and can be updated to `"ApplePaySessionResponse"` or left as-is
    - Line ~599: The `.map(payment_types::ApplePaySessionResponse::NoThirdPartySdk)` call should still work — the type automatically wraps `serde_json::Value` in the variant
  - Run `cargo check -p router` to verify compilation

  **Must NOT do**:
  - Do NOT change the `parse_struct` function signature
  - Do NOT modify the `ThirdPartySdk` or `NoSessionResponse` handling paths
  - Do NOT remove the error logging at line ~582-584

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Type annotation change in 2-3 lines
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 5, after Tasks 2 and 4)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 2, 4

  **References**:

  **Pattern References**:
  - `crates/router/src/core/payments/flows/session_flow.rs:576-590` — The parsing block that needs type annotation change
  - `crates/router/src/core/payments/flows/session_flow.rs:598-599` — The `NoThirdPartySdk` variant wrapping (should work unchanged)

  **API/Type References**:
  - `crates/common_utils/src/ext_traits.rs:156-161` — The `parse_struct` function signature — it's generic over `T: Deserialize`, so `serde_json::Value` works as `T` since `Value` implements `Deserialize`

  **WHY Each Reference Matters**:
  - The parsing block is the critical site where the type annotation must change
  - The parse_struct function signature confirms it's generic and accepts `serde_json::Value`
  - The variant wrapping should work automatically since `NoThirdPartySdk` now takes `serde_json::Value`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after session_flow.rs update
    Tool: Bash
    Preconditions: Tasks 1-4 completed
    Steps:
      1. Run `cargo check -p router 2>&1`
      2. Verify zero errors
    Expected Result: Router crate compiles cleanly
    Failure Indicators: Any compilation errors related to type mismatches or missing imports
    Evidence: .sisyphus/evidence/task-5-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 6. Update `bluesnap/transformers.rs` — change parsing type and remove dead import

  **What to do**:
  - In `crates/hyperswitch_connectors/src/connectors/bluesnap/transformers.rs`:
    - Line 7: Remove `NoThirdPartySdkSessionResponse` from the import list
    - Line ~531: Change `let session_response: NoThirdPartySdkSessionResponse` to `let session_response: serde_json::Value`
    - Line ~532: Update the `parse_struct("NoThirdPartySdkSessionResponse")` string argument to `"ApplePaySessionResponse"` (for clearer error messages)
    - Line ~567: The `ApplePaySessionResponse::NoThirdPartySdk(session_response)` call should still work — the type automatically wraps `serde_json::Value`
    - Add `use serde_json;` if not already imported (check existing imports)
  - Run `cargo check -p hyperswitch_connectors` to verify compilation

  **Must NOT do**:
  - Do NOT modify the payment request construction or other fields in the response
  - Do NOT change the base64 decoding logic
  - Do NOT remove other imports from line 7 (e.g., `ApplepaySessionTokenResponse`, `NextActionCall`)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Type annotation + import change
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 6, after Tasks 2 and 4)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 2, 4

  **References**:

  **Pattern References**:
  - `crates/hyperswitch_connectors/src/connectors/bluesnap/transformers.rs:7` — Import line with `NoThirdPartySdkSessionResponse`
  - `crates/hyperswitch_connectors/src/connectors/bluesnap/transformers.rs:531-533` — Parsing block that needs type change
  - `crates/hyperswitch_connectors/src/connectors/bluesnap/transformers.rs:567-569` — Variant wrapping that should work unchanged

  **WHY Each Reference Matters**:
  - The import must be removed to avoid dead code warnings
  - The type annotation is the critical change
  - The variant wrapping should work automatically

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after bluesnap transformers update
    Tool: Bash
    Preconditions: Tasks 1-4 completed
    Steps:
      1. Run `cargo check -p hyperswitch_connectors 2>&1`
      2. Verify zero errors and zero unused_imports warnings
    Expected Result: Crate compiles cleanly with no warnings about NoThirdPartySdkSessionResponse
    Failure Indicators: Any compilation errors or dead code warnings
    Evidence: .sisyphus/evidence/task-6-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 7. Update OpenAPI generator files — remove `NoThirdPartySdkSessionResponse` schema registration

  **What to do**:
  - In `crates/openapi/src/openapi.rs` (around line 631):
    - Remove the line referencing `api_models::payments::NoThirdPartySdkSessionResponse`
  - In `crates/openapi/src/openapi_v2.rs` (around line 554):
    - Remove the line referencing `api_models::payments::NoThirdPartySdkSessionResponse`
  - Run `cargo check -p openapi` to verify compilation

  **Must NOT do**:
  - Do NOT remove `ApplePaySessionResponse` from the schema registration
  - Do NOT remove `ThirdPartySdkSessionResponse` from the schema registration
  - Do NOT modify any other schema registrations

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Two-line removal
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 7, after Task 2)
  - **Blocks**: Task 8
  - **Blocked By**: Task 2

  **References**:

  **Pattern References**:
  - `crates/openapi/src/openapi.rs:628,631` — Schema registration for `ApplePaySessionResponse` and `NoThirdPartySdkSessionResponse`
  - `crates/openapi/src/openapi_v2.rs:552,554` — Same for v2

  **WHY Each Reference Matters**:
  - These lines register the struct in the OpenAPI schema — the struct no longer exists, so registration must be removed
  - Keep the `ApplePaySessionResponse` registration (it still exists, just with `serde_json::Value` inside)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Compile check after OpenAPI generator update
    Tool: Bash
    Preconditions: Tasks 1-4 completed
    Steps:
      1. Run `cargo check -p openapi 2>&1`
      2. Verify zero errors
    Expected Result: OpenAPI crate compiles cleanly
    Failure Indicators: Any compilation errors about missing types
    Evidence: .sisyphus/evidence/task-7-compile-check.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 8. Regenerate OpenAPI specification JSON files

  **What to do**:
  - Run `cargo r -p openapi --features v1` to regenerate `api-reference/v1/openapi_spec_v1.json`
  - Run `cargo r -p openapi --features v2` to regenerate `api-reference/v2/openapi_spec_v2.json`
  - Verify the generated files no longer contain `NoThirdPartySdkSessionResponse` schema definitions

  **Must NOT do**:
  - Do NOT manually edit the JSON files — they are auto-generated
  - Do NOT skip this step — stale schemas will have broken `$ref` pointers

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Two command runs + verification
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 8, after Task 7)
  - **Blocks**: Task 9
  - **Blocked By**: Task 7

  **References**:

  **Pattern References**:
  - `api-reference/README.md` — Documents the regeneration commands

  **WHY Each Reference Matters**:
  - The README confirms the exact commands to run for spec regeneration

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: OpenAPI v1 spec regeneration and verification
    Tool: Bash
    Preconditions: Task 7 completed
    Steps:
      1. Run `cargo r -p openapi --features v1`
      2. Run `grep -c "NoThirdPartySdkSessionResponse" api-reference/v1/openapi_spec_v1.json`
      3. Verify count is 0
    Expected Result: Zero references to NoThirdPartySdkSessionResponse in v1 spec
    Failure Indicators: Any remaining references
    Evidence: .sisyphus/evidence/task-8-v1-spec-grep.txt

  Scenario: OpenAPI v2 spec regeneration and verification
    Tool: Bash
    Preconditions: Task 7 completed
    Steps:
      1. Run `cargo r -p openapi --features v2`
      2. Run `grep -c "NoThirdPartySdkSessionResponse" api-reference/v2/openapi_spec_v2.json`
      3. Verify count is 0
    Expected Result: Zero references to NoThirdPartySdkSessionResponse in v2 spec
    Failure Indicators: Any remaining references
    Evidence: .sisyphus/evidence/task-8-v2-spec-grep.txt
  ```

  **Commit**: NO (groups with all tasks)

- [x] 9. Final verification sweep — confirm zero remaining references and clean build

  **What to do**:
  - Run `cargo check --all-targets` to verify the entire workspace compiles
  - Run `grep -r "NoThirdPartySdkSessionResponse" crates/ api-reference/` to confirm zero remaining references
  - Run `grep -n "Eq" crates/api_models/src/payments.rs | grep -E "ApplePaySessionResponse|ApplepaySessionTokenResponse|SessionToken"` to confirm `Eq` is removed from all three types
  - Run `cargo check -p smithy` to verify Smithy model generation works with `serde_json::Value` → `smithy.api#Document` mapping
  - Document any warnings and confirm they are acceptable

  **Must NOT do**:
  - Do NOT add `#[allow(dead_code)]` or `#[allow(unused_imports)]` to suppress warnings
  - Do NOT mark complete if any `NoThirdPartySdkSessionReference` references remain

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Verification commands only
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Step 9, after all previous tasks)
  - **Blocks**: Final verification wave
  - **Blocked By**: Tasks 5, 6, 8

  **References**:

  **Pattern References**:
  - All previous task reference locations

  **WHY Each Reference Matters**:
  - Final sweep ensures no stale references remain anywhere in the codebase

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full workspace compilation
    Tool: Bash
    Preconditions: All previous tasks completed
    Steps:
      1. Run `cargo check --all-targets 2>&1`
      2. Verify exit code is 0
    Expected Result: Zero compilation errors across entire workspace
    Failure Indicators: Any compilation errors
    Evidence: .sisyphus/evidence/task-9-full-compile.txt

  Scenario: Zero remaining NoThirdPartySdkSessionResponse references
    Tool: Bash
    Preconditions: All previous tasks completed
    Steps:
      1. Run `grep -r "NoThirdPartySdkSessionResponse" crates/ api-reference/`
      2. Verify zero output lines
    Expected Result: Zero matches — struct fully removed from codebase
    Failure Indicators: Any remaining references
    Evidence: .sisyphus/evidence/task-9-zero-refs.txt

  Scenario: Eq removed from all three cascading types
    Tool: Bash
    Preconditions: All previous tasks completed
    Steps:
      1. Run `grep -n "Eq" crates/api_models/src/payments.rs | grep -E "ApplePaySessionResponse|ApplepaySessionTokenResponse|SessionToken"`
      2. Verify zero matches for Eq on these types
    Expected Result: No Eq derive on any of the three types
    Failure Indicators: Any remaining Eq derive
    Evidence: .sisyphus/evidence/task-9-eq-removed.txt
  ```

  **Commit**: YES
  - Message: `refactor(applepay): treat merchant session response as opaque JSON`
  - Files: all changed files
  - Pre-commit: `cargo check --all-targets`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `cargo check --all-targets` + `cargo clippy`. Review all changed files for: dead code, unused imports, missing type annotations. Check AI slop: excessive comments, over-abstraction.
  Output: `Build [PASS/FAIL] | Clippy [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Verify the serialization behavior: confirm that a mock Apple Pay session JSON response round-trips correctly through the `serde_json::Value` type. Verify `grep -r "NoThirdPartySdkSessionResponse" crates/ api-reference/` returns zero matches.
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance.
  Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

- **Single commit**: `refactor(applepay): treat merchant session response as opaque JSON`
  - Files: all changed files
  - Pre-commit: `cargo check --all-targets`

---

## Success Criteria

### Verification Commands
```bash
cargo check --all-targets                                    # Expected: zero errors
grep -r "NoThirdPartySdkSessionResponse" crates/ api-reference/  # Expected: zero matches
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] `cargo check --all-targets` passes
- [ ] Zero references to `NoThirdPartySdkSessionResponse` remain
