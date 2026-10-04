# GenLayer SDK Surface — Verified Locally

This file records the SDK surface that was **empirically confirmed** by running
`contracts/tests/test_probe_api.py` under `genlayer-test` Direct Mode in this
repository. It supersedes recollection, blog posts, and prose documentation.

Probe command:

```bash
.venv/bin/gltest contracts/tests/test_probe_api.py -v -s
```

## Environment as actually resolved

| Item | Value |
|---|---|
| Python SDK package | `genlayer-py @ git+https://github.com/genlayerlabs/genlayer-py@v0.18` |
| Test framework | `genlayer-test @ git+https://github.com/genlayerlabs/genlayer-testing-suite@v0.29` (installed 0.29.2) |
| Linter | `genvm-linter` (installed 0.11.1rc2), console script `genvm-lint` |
| Contract `Depends` header | `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| Networks known to `gltest` | `localnet`, `studionet`, `testnet_asimov`, `testnet_bradbury` |
| GenLayer CLI (`genlayer`) | npm package `genlayer`, version `0.40.0-rc.3` |

Note: the PyPI package named `genlayer` is a **0.0.1 placeholder with no
entry points** and is not the SDK. The real distribution comes from the
`genlayerlabs` git URLs above, which are what
`genlayerlabs/genlayer-project-boilerplate/requirements.txt` pins.

## Confirmed-available SDK surface

Probed from inside a live Direct Mode VM:

| Symbol | Present |
|---|---|
| `gl.eq_principle.strict_eq` | yes |
| `gl.eq_principle.prompt_comparative` | yes |
| `gl.eq_principle.prompt_non_comparative` | yes |
| `gl.vm.run_nondet` | yes |
| `gl.vm.run_nondet_unsafe` | yes |
| `gl.vm.spawn_sandbox` | yes |
| `gl.vm.Return`, `gl.vm.Result`, `gl.vm.ResultCode`, `gl.vm.UserError`, `gl.vm.VMError` | yes |
| `gl.nondet.exec_prompt` | yes |
| `gl.nondet.web` (with `.render`) | yes |
| `gl.nondet.image` (as `Image`) | yes |
| `gl.vm.unpack_result` | yes |

## Confirmed-absent

These were checked explicitly and **do not exist** in this SDK version. Do not
write contracts against them:

| Symbol | Present |
|---|---|
| `allow_storage` (bare decorator) | **no** |
| `gl.storage.allow` | **no** |
| `gl.vm.run_nondet_default` | **no** |
| `gl.message.get_current_timestamp()` | **no** |
| `gl.message.sender_address.as_hex` | no — use the `Address` value directly |
| `DynArray(...)` construction in contract code | **no** — storage type only |

## Storage constraints discovered by running

These cost real debugging time and are recorded so they are not rediscovered:

1. **Bare `int` is not a storage type.** Use `u256`. Symptom:
   `use 'bigint' or one of sized integers please`.
2. **`DynArray` cannot be instantiated by contract code.** `DynArray.__init__`
   raises unconditionally. To return a constant list from a view, return a
   plain `list[str]`. To persist a fixed-shape tuple of strings, store one
   delimited string.
3. **Nested `TreeMap` does not auto-vivify.** `self.revision[case_id][n] = x`
   raises `KeyError`. Use
   `self.revision.get_or_insert_default(case_id)[n] = x`.
4. **There is no on-chain timestamp.** `gl.message` is a NamedTuple of
   `contract_address`, `sender_address`, `origin_address`, `value`,
   `chain_id`. The VM warps `datetime.datetime.now()` to block time (this is
   what `vm.warp()` drives), so `datetime.datetime.now().timestamp()` is the
   deterministic clock to use.
5. **`u256` has no `.to_s()`** in Direct Mode; use `str(value)`.
6. **`Keccak256` is a factory, not a namespace.** Use
   `Keccak256(payload.encode("utf-8")).digest()`; it returns raw bytes, so hexlify
   it yourself.
7. **The linter requires `gl.vm.UserError("msg")`, not bare `Exception`.** Bare
   `Exception` is only a warning, but `UserError` is a deterministic error that
   validators can compare, so it is the correct choice here.

## Direct Mode mock semantics (verified)

`vm.mock_llm` matches **first registered wins**, iterating in registration
order. Registering a second `mock_llm(r".*", ...)` has no effect while an
earlier `.*` mock is still registered. To change the model's answer mid-test,
call `vm.clear_mocks()` first.

`vm.strict_mocks = True` raises `RuntimeWarning` for any mock never matched.
Tests that expect a revert before any model call will legitimately warn; those
warnings are the mock correctly reporting it was never needed.

## `run_nondet` signature (verbatim from SDK source)

```python
def run_nondet[T: calldata.Decoded](
    leader_fn: typing.Callable[[], T],
    validator_fn: typing.Callable[[Result[T]], bool],
    /,
    *,
    compare_user_errors: typing.Callable[[UserError, UserError], bool] = lambda a, b: a.message == b.message,
    compare_vm_errors: typing.Callable[[VMError, VMError], bool] = lambda a, b: a.message == b.message,
) -> Lazy[T]:
```

`validator_fn` receives a `Result[T]` (which may be `Return`, `VMError`, or
`UserError`) and returns a bool. `gl.vm.unpack_result(res)` extracts the value
and converts `VMError` into a `UserError`. `run_nondet` (not
`run_nondet_unsafe`) runs the validator in a sandbox and applies the
`compare_*` callbacks, so it is the safer default and is what
ForkReasonRegistry uses.

`run_nondet_unsafe(leader_fn, validator_fn)` exists and takes the same
arguments, but the SDK docstring warns it does not sandbox the validator: a
validator error becomes a `Disagree`. Prefer `run_nondet`.

`gl.vm.spawn_sandbox(fn, *, allow_write_ops=False)` runs a callable in an
isolated VM; useful for isolating untrusted computation.

## Contract import form

This form compiles and executes correctly under Direct Mode:

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *


class MyContract(gl.Contract):
    value: str

    def __init__(self, value: str):
        self.value = value

    @gl.public.write
    def set_value(self, new_value: str) -> None:
        self.value = new_value

    @gl.public.view
    def get_value(self) -> str:
        return self.value
```

Verified working via `contracts/tests/test_probe_api.py`.

## Correction to the published docs

Prose documentation and third-party summaries diverge from the shipped SDK. Two
specific claims that were checked and found **false** for this version:

1. `gl.vm.run_nondet_default` — documented in places, absent here. Use
   `gl.vm.run_nondet` and `gl.vm.run_nondet_unsafe`.
2. `@allow_storage` — documented for decorated storage dataclasses, absent
   here. Do not use it.

The authoritative procedure for this repository is therefore: **probe, then
write**. When a contract needs an API that has not been verified here, add it to
the probe contract and re-run before relying on it.

## Direct Mode test surface

Fixtures provided by `gltest.direct.pytest_plugin`: `direct_vm`, `direct_deploy`,
`direct_alice`, `direct_bob`, `direct_charlie`, `direct_owner`,
`direct_accounts`.

`VMContext` cheatcodes:

| Cheatcode | Purpose |
|---|---|
| `vm.sender` | set transaction sender |
| `vm.mock_web(pattern, {"status": ..., "body": ...})` | mock `gl.nondet.web.render` |
| `vm.mock_llm(pattern, response_str)` | mock `gl.nondet.exec_prompt` |
| `vm.strict_mocks` | fail if a mock is unused |
| `vm.run_validator(leader_result=..., leader_error=..., index=N)` | run an independent validator |
| `vm.clear_validators()` | reset validator state |
| `vm.expect_revert(message)` | assert revert |
| `vm.warp(timestamp)` | warp chain time |
| `vm.snapshot()` / `vm.revert(id)` | state snapshots |
| `vm.deal(address, amount)` | balance cheatcode |
| `vm.prank(address)` | impersonate sender |

Signatures (verified from
`.venv/lib/python3.12/site-packages/gltest/direct/loader.py`):

```python
deploy_contract(contract_path: Path, vm: VMContext, *args, sdk_version=None, **kwargs)
load_contract_class(contract_path: Path, vm: VMContext, sdk_version=None)
create_address(seed: str)
create_test_addresses(count: int = 10)
```

`deploy_contract` takes a `Path`, and constructor arguments are positional after
`vm`.

## Studio Mode (integration) surface

From the official boilerplate's `tests/integration`:

```python
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

@pytest.mark.integration
def test_x():
    factory = get_contract_factory("FootballBets")
    contract = factory.deploy()
    result = contract.create_bet(args=["2024-06-20", "Spain", "Italy", "1"])
    assert tx_execution_succeeded(result)
    state = contract.get_bets(args=[])
```

Studio Mode requires a running GenLayer Studio node (the `genlayer` npm CLI with
Docker). Config lives in `gltest.config.yaml`:

```yaml
networks:
  default: studionet
  studionet: {}
  localnet:
    url: "http://127.0.0.1:4000/api"
paths:
  contracts: "contracts"
environment: .env
```

## Documentation-vs-SDK policy for this project

Where prose docs and the probed SDK disagree, **the probed SDK wins** and the
discrepancy is recorded here. Contract code is written against verified symbols
only.