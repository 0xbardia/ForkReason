# GenLayer Intelligent Contracts — Python SDK Reference (CURRENT)

**Verified:** 2026-10-03 against `genlayerlabs/genvm` @ `main` (latest release `v0.3.0-rc7`, stable `v0.2.16`),
`genlayerlabs/genlayer-docs` @ `main`, `genlayerlabs/genlayer-testing-suite` @ `main`.

**Sources of truth used (in priority order)**
1. `https://github.com/genlayerlabs/genvm` → `runners/genlayer-py-std/src/genlayer/` — the actual SDK source.
2. `https://github.com/genlayerlabs/genlayer-testing-suite` → `tests/examples/contracts/*.py` — working, CI-exercised contracts.
3. `https://docs.genlayer.com` (source: `genlayerlabs/genlayer-docs`) — prose, used for intent and warnings.

> ⚠️ **READ THIS FIRST — the published docs and the shipping SDK disagree in several places.**
> Section 2 lists every divergence with the corrected form. Code copied from `docs.genlayer.com`
> **as of today will fail** on the items marked ✗. The SDK source is authoritative.

---

## 1. The canonical contract form

There are two competing forms in the wild. **Use form A.**

### ✅ Form A — current SDK (what the working example contracts use)

```python
# { "Depends": "py-genlayer:latest" }

import genlayer as gl

class WizardOfCoin(gl.contract.Contract):
    have_coin: bool

    def __init__(self, have_coin: bool):
        self.have_coin = have_coin

    @gl.public.write
    def ask_for_coin(self, request: str) -> None:
        prompt = f"...Respond as JSON: {{\"give_coin\": bool}}"

        def leader_fn():
            return gl.nondet.exec_prompt(prompt)

        result = gl.eq_principle.prompt_comparative(
            leader_fn, "The value of give_coin has to match"
        )
        self.have_coin = not json.loads(result)["give_coin"]

    @gl.public.view
    def get_have_coin(self) -> bool:
        return self.have_coin
```

Verbatim from `genlayer-testing-suite/tests/examples/contracts/wizard_of_coin.py` (CI-exercised):

```python
# v0.1.0
# { "Depends": "py-genlayer:latest" }
import genlayer as gl

import json


class WizardOfCoin(gl.contract.Contract):
    have_coin: bool

    def __init__(self, have_coin: bool):
        self.have_coin = have_coin

    @gl.public.write
    def ask_for_coin(self, request: str) -> None:
        if not self.have_coin:
            return
        ...
        def get_wizard_answer():
            result = gl.nondet.exec_prompt(prompt)
            result = result.replace("```json", "").replace("```", "")
            print(result)
            return result

        result = gl.eq_principle.prompt_comparative(
            get_wizard_answer, "The value of give_coin has to match"
        )
        parsed_result = json.loads(result)
        assert isinstance(parsed_result["give_coin"], bool)
        self.have_coin = not parsed_result["give_coin"]
```

### ❌ Form B — what `docs.genlayer.com` shows (partly stale)

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

class MyContract(gl.Contract):     # ✗ not `gl.Contract`
    ...
    @allow_storage                  # ✗ not `allow_storage`; use `gl.storage.allow`
    @dataclass
    class User: ...
```

The pinned hash form still works, but `from genlayer import *` + `gl.Contract` + `@allow_storage`
is the pre-`v0.2` API surface.

### Contract header (`Depends`)

Single dependency:
```python
# { "Depends": "py-genlayer:latest" }
```

Multiple, as a `Seq`:
```python
# {
#   "Seq": [
#     { "Depends": "py-lib-genlayer-embeddings:latest" },
#     { "Depends": "py-genlayer:latest" }
#   ]
# }
```

Profiling via env var inside `Seq`:
```python
# {
#   "Seq": [
#     { "SetEnv": { "name": "GENLAYER_ENABLE_PROFILER", "value": "true" } },
#     { "Depends": "py-genlayer:latest" }
#   ]
# }
```

The runner resolves the header at runtime (`gltest/direct/sdk_loader.py`): `GENVM_VERSION` env var >
newest cached release > newest non-prerelease GitHub release shipping a runner bundle
(`genvm-runners-all.tar.xz`, formerly `genvm-universal.tar.xz`); fallback `v0.2.16`.

---

## 2. Divergences: docs vs. shipping SDK

Every row verified by reading SDK source, not docs prose.

| # | Docs say | SDK actually exports | Status |
|---|---|---|---|
| 1 | `gl.vm.run_nondet_unsafe(leader, validator)` | `gl.vm.run_nondet(leader, validator)` and `gl.vm.run_nondet_default(...)` | ✗ **does not exist** |
| 2 | `@allow_storage` | `gl.storage.allow` (also bare `allow`) | ✗ **does not exist** |
| 3 | `class C(gl.Contract)` | `gl.contract.Contract` | ✗ **does not exist** |
| 4 | `gl.UserError("...")` | `gl.vm.UserError(...)` | ✗ **not exported at top level** |
| 5 | `gl.advanced.user_error_immediate("...")` | `gl.vm.UserError.immediate(...)` | ✗ **no `advanced` module** |
| 6 | `e.message` on a UserError | `e.data` (`.message` exists on `VMError` only) | ✗ **wrong attribute** |
| 7 | `gl.eq_principle.strict_eq` wraps raw LLM output | same | ⚠️ linter rule GL-S03 = **ERROR** |
| 8 | `prompt_non_comparative(input=...)` | first param is positional-only `fn` | ✗ **`input=` is a TypeError** |
| 9 | `response.status_code` | `Response.status` | ✗ **wrong attribute** |
| 10 | `gl.get_contract_at(addr)` | `gl.contract.get_at(addr)` | ✗ **wrong path** |
| 11 | `gl.deploy_contract(...)` | `gl.contract.deploy(...)` | ✗ **wrong path** |
| 12 | `from genlayer import *` | `import genlayer as gl` | ⚠️ star-import works but `gl` must still be imported |

Verified mechanically: `run_nondet_unsafe` appears **nowhere** in `genlayer/vm/__init__.py` at `main`.
The SDK's `vm.__all__` is exactly:

```python
__all__ = (
	'spawn_sandbox',
	'run_nondet',
	'run_nondet_default',
	'unpack_result',
	'Return',
	'VMError',
	'UserError',
	'Result',
	'trace',
	'trace_time_micro',
	'ABI',
)
```

> **Naming trap.** Docs describe `run_nondet_unsafe` as "the *unsafe* one — validator errors are NOT caught,
> they count as Disagree" and `run_nondet` as "the safe one that sandboxes the validator and compares errors".
> That *semantics* is correct, but the *names are swapped* in the current SDK:
> - `run_nondet` = **unsafe** (no extra sandbox; validator exception ⇒ `Disagree`, same as returning `False`)
> - `run_nondet_default` = **safe** (validator runs in a sandbox; errors compared via callbacks)
>
> So when docs say `run_nondet_unsafe`, read `gl.vm.run_nondet`. When they say `run_nondet` in the
> "convenience functions" table, read `gl.vm.run_nondet_default`.

---

## 3. Core API signatures (verbatim from SDK source)

### 3.1 `gl.vm` — result types and consensus

```python
@dataclasses.dataclass
class Return[T: calldata.Decoded]:
	calldata: T

@dataclasses.dataclass
class VMError:
	message: str

class UserError(Exception):
	data: calldata.Decoded
	def __init__(self, data: calldata.Decoded, /): ...
	def __str__(self) -> str: return 'UserError(' + repr(self.data) + ')'
	@staticmethod
	def immediate(reason: calldata.Encodable) -> typing.NoReturn: ...

type Result[T: calldata.Decoded] = Return[T] | VMError | UserError
```

```python
def run_nondet[T: calldata.Decoded](
	leader_fn: typing.Callable[[], T],
	validator_fn: typing.Callable[[Result], bool],
	/,
) -> Lazy[T]:
	"""
	This function does not use extra sandbox for catching validator errors.
	Validator error will result in a ``Disagree`` error in executor (same as if
	this function returned ``False``). Use run_nondet_default instead if you
	want to catch and inspect ``validator_fn`` errors, or use sandbox inside of it.
	"""
```

```python
def run_nondet_default[T: calldata.Decoded](
	leader_fn: typing.Callable[[], T],
	validator_fn: typing.Callable[[Result[T]], bool],
	/,
	*,
	compare_user_errors: typing.Callable[[UserError, UserError], bool] = lambda a, b: a.data == b.data,
	compare_vm_errors: typing.Callable[[VMError, VMError], bool] = lambda a, b: a.message == b.message,
) -> Lazy[T]:
	"""
	Executes a non-deterministic block with comprehensive error handling.

	This is the recommended API for custom non-deterministic execution.
	"""
```

```python
def spawn_sandbox[T: calldata.Decoded](
	fn: typing.Callable[[], T], *, allow_write_ops: bool = False
) -> Lazy[Return[T] | VMError | UserError]

def unpack_result[T: calldata.Decoded](res: Result[T], /) -> T
	# raises UserError on UserError; rewraps VMError as UserError('vm error: ' + message)

def trace(*objs: typing.Any, sep: str = ' ')          # -> genvm_log
def trace_time_micro() -> int                          # needs GENLAYER_ENABLE_PROFILER=true
```

**Validator shape.** The validator always receives a `Result`, never a bare value:

```python
def validator_fn(leader_result) -> bool:
    if not isinstance(leader_result, gl.vm.Return):
        return False           # leader errored -> reject
    data = leader_result.calldata
    ...
```

Note the SDK default `compare_user_errors` compares **`a.data == b.data`** — i.e. `UserError` messages
are compared by exact equality of `.data`, not by `.message`.

### 3.2 `gl.eq_principle`

```python
def strict_eq[T: calldata.Decoded](fn: typing.Callable[[], T], /) -> Lazy[T]
    # runs fn on all validators; results must be strictly equal.
    # internally: vm.spawn_sandbox(fn) == leaders_res

def prompt_comparative[T: calldata.Decoded](
	fn: typing.Callable[[], T], principle: str, /
) -> Lazy[T]
    # internally: vm.run_nondet_default

def prompt_non_comparative(
	fn: typing.Callable[[], str], /, *, task: str, criteria: str
) -> Lazy[str]
    # internally: vm.run_nondet_default
```

`prompt_non_comparative` — **`fn` is positional-only; `task` and `criteria` are keyword-only.**
Docs showing `prompt_non_comparative(input="...", task=..., criteria=...)` will raise `TypeError`.
Correct:

```python
result = gl.eq_principle.prompt_non_comparative(
    lambda: gl.nondet.web.get(url).body.decode("utf-8"),
    task="Summarize this article in 2-3 sentences",
    criteria="""
        Summary must capture the main point of the article
        Must not include information not present in the source
        Must be 2-3 sentences long
    """,
)
```

**Templates.** `prompt_comparative` uses template `EqComparative`; `prompt_non_comparative` uses
`EqNonComparativeLeader` (leader) and `EqNonComparativeValidator` (validator). To use a template
inside your own validator you must call the internal path (import paths are unstable):

```python
import genlayer.gl._internal.gl_call as gl_call
from genlayer.gl.nondet import _decode_nondet

verdict = gl_call.gl_call_generic(
    {
        'ExecPromptTemplate': {
            'template': 'EqComparative',
            'leader_answer': format(leader_result.calldata),
            'validator_answer': format(validator_data),
            'principle': "`outcome` must match exactly. Reasoning may differ.",
        }
    },
    _decode_nondet,
).get()
```

### 3.3 `gl.nondet` — LLM + web

```python
def exec_prompt(prompt: str, /, **config: ExecPromptKwArgs) -> Lazy[str | dict]
```

`ExecPromptKwArgs` (TypedDict):
```python
class ExecPromptKwArgs(typing.TypedDict):
	response_format: typing.NotRequired[typing.Literal['text', 'json']]   # defaults to 'text'
	images: typing.NotRequired[collections.abc.Sequence[bytes | Image] | None]
```

Overloads:
```python
def exec_prompt(prompt: str, *, images: Sequence[bytes | Image] | None = None) -> str
def exec_prompt(prompt: str, *, response_format: Literal['text'], images: ... = None) -> str
def exec_prompt(prompt: str, *, response_format: Literal['json'], image: bytes | Image | None = None) -> dict
```
Behavioural details worth knowing:
- `response_format='json'` is mapped internally to `'json2'` and decoded with `json.loads` ⇒ you get a **`dict`**, not a string.
- Empty prompt raises `ValueError('Prompt cannot be empty')`.
- Image limit is **two** per call.

`Image`:
```python
@dataclasses.dataclass
class Image:
	raw: bytes
	pil: 'PIL.Image.Image'
```

Web (`gl.nondet.web`):
```python
@dataclasses.dataclass
class Response:
	status: int                      # ✗ NOT .status_code
	headers: dict[str, bytes]
	body: bytes | None               # ✗ may be None — .decode() on None blows up

def get(url, /, *, headers={}, sign=False) -> Lazy[Response]
def post(url, /, *, body=None, headers={}, sign=False) -> Lazy[Response]
def put(url, /, *, body=None, headers={}, sign=False) -> Lazy[Response]
def delete(url, /, *, body=None, headers={}, sign=False) -> Lazy[Response]
def head(url, /, *, body=None, headers={}, sign=False) -> Lazy[Response]
def patch(url, /, *, body=None, headers={}, sign=False) -> Lazy[Response]
def request(url, /, *, method: Literal['GET','POST','PUT','DELETE','HEAD','OPTIONS','PATCH'],
            body=None, headers={}, sign=False) -> Lazy[Response]

def render(url, /, *, mode: Literal['html','text','screenshot'] = 'text',
           wait_after_loaded: str | None = None) -> Lazy[str | Image]
```
`mode='screenshot'` returns an `Image`. `wait_after_loaded` format: `"1000ms"`, `"1s"`.

```python
class NondetException(Exception):
	causes: list[str]
	ctx: dict[str, typing.Any]
```

### 3.4 `gl.message` — transaction context

Typed module-level attributes (not a `NamedTuple` object; `gl.message.X` is a plain attribute):

| Field | Type | Meaning |
|---|---|---|
| `contract_address` | `Address` | this IC's own address |
| `sender_address` | `Address` | immediate caller (EOA / EVM contract / IC) |
| `origin_address` | `Address` | original tx submitter, preserved across internal message chains |
| `value` | `u256` | GEN sent with the call (payable methods only) |
| `chain_id` | `u256` | current chain ID |
| `datetime` | `str` | ISO 8601 transaction datetime |
| `is_init` | `bool` | `True` iff this execution is a deployment |
| `stack` | `list[Address]` | view-caller stack, excluding this contract |
| `entry_kind` | `int` | `0`=MAIN, `1`=SANDBOX, `2`=CONSENSUS_STAGE |
| `entry_data` | `bytes` | raw entry payload |
| `entry_stage_data` | `Decoded` | consensus-stage data |
| `raw` | `MessageRawType` | the whole TypedDict above |

**Clock is pinned to transaction time**, not host wall-clock:
```python
from datetime import datetime, timezone
now = int(datetime.now(timezone.utc).timestamp())     # == int(time.time())
iso  = datetime.now(timezone.utc).isoformat()          # == gl.message_raw['datetime']
```
No block number, no block hash, no gas price, no nonce.

### 3.5 `gl.public` / `gl.private` decorators

```python
class public:
	@staticmethod
	def view(f, /): ...        # public + readonly
	write = _write()           # public + not readonly; has .payable and .min_gas(...)

class _write(_payable):
	def min_gas(self, *, leader: int, validator: int) -> _min_gas
	def payable[T](self, f: T, /) -> T
	def __call__[T](self, f: T) -> T

def private(f, /)   # no-op; all methods are private by default
```

Usage:
```python
@gl.public.view
def get_x(self) -> str: ...

@gl.public.write
def set_x(self, v: str): ...

@gl.public.write.payable
def deposit(self): ...

@gl.public.write.min_gas(leader=100, validator=20).payable
def heavy(self): ...
```
Rules: exactly **one** contract class per file; `__init__` must be private (undecorated);
a `@gl.public.write` method called with non-zero `value` reverts unless marked `.payable`.

### 3.6 Storage

Type substitutions for persisted fields (class-body annotations only — assigning
`self.x` for an undeclared field is silently discarded):

| Instead of | Use |
|---|---|
| `list[T]` | `DynArray[T]` |
| `dict[K, V]` | `TreeMap[K, V]` |
| bare `int` | `u8` … `u256`, `i8` … `i256`, or `bigint` |

Generics must be **fully instantiated** — `TreeMap` bare is an error, `TreeMap[str, u256]` is fine.

Custom storage types:
```python
@gl.storage.allow
@dataclass
class User:
	name: str
	age: u8
	balance: u256
```
`@gl.storage.allow` is the current name (`allow` is exported bare too). Docs' `@allow_storage` is dead.

Helpers:
```python
gl.storage.inmem_allocate[T](t: typing.Type[T], /, *init_args, **init_kwargs) -> T
gl.storage.copy_to_memory[T](val: T, /) -> T     # required before using storage in a nondet block
gl.storage.Pickled[T]().store(val) / .load()      # pickle arbitrary objects into storage
gl.storage.Array, gl.storage.DynArray, gl.storage.TreeMap
```

Zero-init defaults: `u*/i*`→`0`, `bool`→`False`, `float`→`0.0`, `str`→`""`, `bytes`→`b""`,
`Address`→`0x0…`, `DynArray`→`[]`, `TreeMap`→`{}`.

Sized ints are `typing.Annotated[int, StaticIntMeta(size_bytes, signed)]` — they behave like plain
`int` in expressions; **range checks fire only on assignment into storage**.

### 3.7 `Address`

```python
class Address:
	SIZE: typing.Final[int] = 20
	ZERO: typing.ClassVar['Address']

	def __init__(self, val: 'str | collections.abc.Buffer | Address'): ...
	#   str → 0x-prefixed 42-char hex, else treated as base64
	#   ⚠ checksum validation is NOT performed

	as_bytes -> bytes
	as_hex   -> str     # EIP-55 checksummed
	as_b64   -> str
	as_int   -> u160    # little-endian!
	__format__(fmt: Literal['s','x','b64','cd',''])
```

### 3.8 Contract interaction

```python
gl.contract.get_at(address: Address, /) -> Proxy
gl.contract.deploy(...)
gl.contract.interface              # @interface decorator for typed IC stubs
gl.evm.contract_interface          # @contract_interface for EVM stubs
```

`Proxy` protocol:
```python
def view(self, *, state: StorageType = StorageType.LATEST_NON_FINAL) -> TView
def emit(self, *, value: u256 = 0, on: ON = 'finalized') -> TSend
def emit_transfer(self, value: u256, *, on: ON = 'finalized') -> None
@property
def balance -> u256
@property
def address -> Address
```
`type ON = typing.Literal['accepted', 'finalized']`.

```python
other = gl.contract.get_at(addr)
other.view().get_balance()                     # synchronous read
other.emit(on='finalized').update_status("x")  # async write, after finalization
other.emit(value=u256(100), on='finalized').deposit()
other.emit_transfer(value=u256(100), on='finalized')
```
`emit_transfer` raises `ValueError` on zero value. Internal-message senders see
`gl.message.sender_address` = calling contract, `origin_address` = original caller.

`on='accepted'` is genuinely risky: on appeal the message **cannot be recalled** and may be
re-emitted up to ~6 times across appeal rounds. Receivers must be idempotent. External (EVM) messages
are `finalized`-only.

### 3.9 Special methods

```python
class C(gl.contract.Contract):
	@gl.public.write.payable                    # or plain @gl.public.write
	def __handle_undefined_method__(
		self, method_name: str, args: list[typing.Any], kwargs: dict[str, typing.Any]
	): ...

	@gl.public.write.payable
	def __receive__(self): ...
```
`__handle_undefined_method__` must be `@gl.public.write` or `@gl.public.write.payable`;
`__receive__` must be `.payable`. Methods starting with `__` cannot be called externally —
the bootloader raises `ValueError('calls to methods that start with __ is forbidden')`.

### 3.10 Upgradability

```python
class Root:
	contract_instance: Indirection[None]
	code: Indirection[VLA[u8]]
	locked_slots: Indirection[VLA[u256]]
	upgraders: Indirection[VLA[Address]]
	major: u8

	@staticmethod
	def get() -> 'Root'
	def slot(self) -> Slot
	def get_vacant_slot(self) -> Slot
	def get_contract_instance[T](self, typ: typing.Type[T], /) -> T
	def lock_default(self)
```

Flow: after `__init__`, the bootloader calls `root_slot.lock_default()` automatically, freezing
root / code / locked_slots / upgraders. A sender **in** `upgraders` bypasses slot locks and may
rewrite `code`. Storage layout must stay compatible across upgrades — no migration mechanism.

```python
def __init__(self, initial: str):
    self.storage = initial
    root = gl.storage.Root.get()
    root.upgraders.get().append(gl.message.sender_address)

@gl.public.write
def upgrade(self, new_code: bytes) -> None:
    code = gl.storage.Root.get().code.get()
    code.truncate()
    code.extend(new_code)
```

---

## 4. Testing — `genlayer-test`

```bash
pip install genlayer-test          # Direct + Studio modes
pip install genlayer-test[sim]     # + glsim local network
```

| | Direct Mode | Studio Mode |
|---|---|---|
| Runs | in-process, no network | Studio via RPC |
| Speed | ms/test | minutes/test |
| Needs | Python 3.12+ | Python 3.12+ + Studio (Docker) |
| Mocking | `mock_web` / `mock_llm` cheatcodes | mock validators via transaction context |

### 4.1 Direct Mode — exact signatures

Fixtures: `direct_vm`, `direct_deploy`, `direct_alice`, `direct_bob`, `direct_charlie`,
`direct_owner`, `direct_accounts` (10 addresses).

```python
def test_storage(direct_deploy):
    storage = direct_deploy("contracts/Storage.py", "initial value")
    assert storage.get_storage() == "initial value"
    storage.update_storage("updated")
    assert storage.get_storage() == "updated"
```

Module-level API (`gltest.direct.loader`):
```python
def deploy_contract(contract_path: Path, vm: "VMContext", *args: Any,
                    sdk_version: Optional[str] = None, **kwargs: Any) -> Any
def load_contract_class(contract_path: Path, vm: "VMContext",
                        sdk_version: Optional[str] = None) -> Type[Any]
def create_address(seed: str) -> Any
def create_test_addresses(count: int = 10) -> list
```
> Docs render `deploy_contract(..., args: Any, ...)`; source is `*args, **kwargs`.
> Constructor args are **variadic** — `direct_deploy(path, "a", 1, True)`, not a list.

`VMContext` cheatcodes:
```python
def mock_web(self, url_pattern: str, response: MockedWebResponseData) -> None
def mock_llm(self, prompt_pattern: str, response: str) -> None
def clear_mocks(self) -> None
def snapshot(self) -> int
def revert(self, snapshot_id: int) -> None
def deal(self, address: Any, amount: int) -> None
def warp(self, timestamp: str) -> None              # ISO format
def prank(self, address: Any)                      # context manager
def startPrank(self, address: Any) -> None
def stopPrank(self) -> None
def expect_revert(self, message: Optional[str] = None)   # context manager
def activate(self)

def run_validator(self, *, leader_result: Any = _sentinel,
                  leader_error: Optional[Exception] = None,
                  index: int = -1) -> bool
def clear_validators(self) -> None

# properties
sender, value, origin            # settable
check_pickling: bool             # validate pickling of run_nondet closures
strict_mocks: bool               # warn/raise on unused mocks
```

⚠️ **`run_validator` is keyword-only** (`*` in the signature). The published Direct Mode reference
renders it as positional — `vm.run_validator(leader_result, leader_error, index)` — which raises
`TypeError`. Correct:

```python
direct_vm.run_validator()                                  # last captured, real leader result
direct_vm.run_validator(leader_result={"verdict": "x"})
direct_vm.run_validator(leader_error=gl.vm.UserError("boom"))
direct_vm.run_validator(index=-2)
```

Patterns:
```python
# sender control
direct_vm.sender = direct_alice
with direct_vm.prank(direct_bob):
    with direct_vm.expect_revert("Unauthorized"):
        contract.owner_action()

# snapshots capture storage + balances + mocks + prank stack + captured validators + sender/origin/value/chain_id
snap = direct_vm.snapshot()
contract.increment()
direct_vm.revert(snap)

# mocking (regex patterns)
direct_vm.mock_web(r"api\.example\.com/price", {"status": 200, "body": '{"price": 42.50}'})
direct_vm.mock_llm(r"classify.*sentiment", "positive")

# consensus testing
contract.update_price()                  # leader runs; validator captured
direct_vm.clear_mocks()
direct_vm.mock_llm(r".*", '{"verdict": "false"}')
assert direct_vm.run_validator() is False
```

### 4.2 Studio Mode

```python
from gltest import get_contract_factory, get_default_account, get_validator_factory
from gltest.assertions import tx_execution_succeeded, tx_execution_failed

factory = get_contract_factory("Storage")            # or contract_file_path=Path(...)
contract = factory.deploy(args=["initial_value"], account=get_default_account(),
                          consensus_max_rotations=3)

result = contract.get_storage().call()               # read
tx = contract.update_storage(args=["new value"]).transact(value=0, consensus_max_rotations=3)
assert tx_execution_succeeded(tx)
```

Signatures:
```python
def get_contract_factory(contract_name: Optional = None, contract_file_path: Union = None) -> ContractFactory
def get_default_account() -> LocalAccount
def get_accounts() -> List
def create_accounts(n_accounts: int)
def get_gl_client()
def get_validator_factory() -> ValidatorFactory

factory.deploy(args=None, account=None, consensus_max_rotations=None, wait_interval=None,
               wait_retries=None, wait_transaction_status=TransactionStatus.ACCEPTED,
               wait_triggered_transactions=False,
               wait_triggered_transactions_status=TransactionStatus.ACCEPTED,
               transaction_context=None) -> Contract
factory.deploy_contract_tx(...same...) -> GenLayerTransaction
factory.build_contract(contract_address, account=None) -> Contract

contract.m.call(transaction_hash_variant=TransactionHashVariant.LATEST_NONFINAL,
                transaction_context=None)
contract.m.transact(value=0, consensus_max_rotations=None,
                    wait_transaction_status=TransactionStatus.ACCEPTED, wait_interval=None,
                    wait_retries=None, wait_triggered_transactions=False,
                    wait_triggered_transactions_status=TransactionStatus.ACCEPTED,
                    transaction_context=None)
contract.m.analyze(provider, model, config=None, plugin=None, plugin_config=None,
                   runs=100, genvm_datetime=None)

assert tx_execution_succeeded(tx, match_std_out=r".*code \d+")
assert tx_execution_failed(tx, match_std_err=r"Method.*failed")
```

`gltest.config.yaml`:
```yaml
networks:
  default: localnet
  localnet:
    url: "http://127.0.0.1:4000/api"
    leader_only: false
  studionet:
  testnet_asimov:
    accounts:
      - "${ACCOUNT_PRIVATE_KEY_1}"
    from: "${ACCOUNT_PRIVATE_KEY_1}"
paths:
  contracts: "contracts"
  artifacts: "artifacts"
environment: .env
```
CLI: `gltest tests/ -v`, `gltest --network studionet`, `gltest --leader-only`,
`--contracts-dir`, `--rpc-url`, `--chain-type`.

Mock validator maps (`MockedLLMResponse` keys ⇒ SDK methods, **substring** matched):
`"nondet_exec_prompt"` ⇒ `gl.nondet.exec_prompt`;
`"eq_principle_prompt_comparative"`; `"eq_principle_prompt_non_comparative"`.
Web mocks (`MockedWebResponse`, key `"nondet_web_request"`) are **exact URL** matches.

### 4.3 glsim — local network without Docker

```bash
pip install genlayer-test[sim]
glsim                                        # port 4000, 5 validators
glsim --port 8000 --validators 3 --llm-provider openai:gpt-4o
glsim --seed my-test-seed                   # deterministic addresses
```
Options: `--port`(4000) `--host`(127.0.0.1) `--validators`(5) `--max-rotations`(3)
`--chain-id`(61127) `--llm-provider` `--no-browser` `--seed` `-v`.
RPC: `gen_call`, `gen_get_contract_schema`, `gen_get_transaction_status`,
`sim_deploy|call|read|fund_account|get_balance|create_snapshot|restore_snapshot|install_mocks|get_mocks|increase_time|set_time`, plus `eth_*`.

---

## 5. Linting — `genvm-linter`

```bash
pip install genvm-linter
genvm-lint check contract.py        # lint + validate
genvm-lint lint contract.py         # AST only, ~50ms
genvm-lint validate contract.py     # full SDK semantic, ~200ms cached
genvm-lint schema contract.py --output abi.json
genvm-lint typecheck contract.py [--strict] [--all]
genvm-lint setup --contract contract.py [--json]
genvm-lint download [--list]
genvm-lint check contract.py --json
```
Exit codes: `0` pass, `1` lint/validation error, `2` file not found, `3` SDK download failed.

**GL-S03 (ERROR).** Flags `strict_eq` wrapping a function that returns **raw** nondeterministic output —
`gl.nondet.exec_prompt`, `gl.exec_prompt`, `gl.get_webpage`, `gl.nondet.web.render`, or bare
`exec_prompt`/`get_webpage` (direct-import style). Detection is conservative: processed output
(`bool` comparisons, `json.loads`, sorted results) is *not* flagged.

```python
# ✗ flagged
gl.eq_principle.strict_eq(lambda: gl.nondet.exec_prompt("What is 2+2?"))

# ✓ not flagged — deterministic bool derived
gl.eq_principle.strict_eq(lambda: "Paris" in gl.get_webpage("https://example.com"))
```

Layer 1 also rejects forbidden imports (`random`, `os`, `time`), non-deterministic patterns
(`float()`, `time.time()`), and a missing dependency header.

---

## 6. Deploying

Two supported paths.

### 6.1 CLI
```bash
npm install -g genlayer
genlayer init && genlayer up

genlayer network set localnet        # default http://localhost:4000/api, chain id 61127
genlayer network list
genlayer network info               # verify effective RPC/chain/explorer before funding

genlayer deploy --contract contracts/my_contract.py --args "World Cup 2024" 1000
genlayer deploy --contract c.py --rpc https://studio.genlayer.com/api

genlayer call <contractAddress> <method>     # read, no state change
genlayer write <contractAddress> <method>    # state-changing tx
genlayer schema <contractAddress>
```
CLI arg types: `str`, `int`, `float`, `bool` (`true`/`false` lowercase). **No lists/dicts/objects** —
use deploy scripts for those.

Built-in network aliases:

| Alias | Target |
|---|---|
| `localnet` | local Studio / GLSim, chain id `61127` |
| `studionet` | stable hosted Studio, chain id `61999` |
| `testnet-asimov` | shared infra / stress testing |
| `testnet-bradbury` | production-like, real AI workloads |
| `studio-dev` | RC preview, chain id `61997` (requires matching RC CLI/SDK) |

Do **not** substitute `studionet` for `studio-dev` — different chain ID and consensus deployment.
Custom profiles: `genlayer network add my-preview --base studionet --rpc … --chain-id … --deployment … --explorer …`.

### 6.2 Deploy scripts (`deploy/*.ts`, run in filename order — use numeric prefixes)

```typescript
import { readFileSync } from 'node:fs';
import { isSuccessful } from 'genlayer-js';
import type { DecodedDeployData, GenLayerClient } from 'genlayer-js/types';

export default async function main(client: GenLayerClient<any>) {
  const code = new Uint8Array(readFileSync(new URL('../contracts/my_contract.py', import.meta.url)));
  const estimate = await client.estimateTransactionFees({
    leaderTimeunitsAllocation: 125n,
    validatorTimeunitsAllocation: 250n,
    executionBudgetPerRound: 786_500n,
    totalMessageFees: 0n,
    appealRounds: 1n,
    rotations: [1n, 1n],
  });

  const txId = await client.deployContract({
    code, args: [],
    fees: { distribution: estimate.distribution, feeValue: estimate.feeValue },
  });

  const transaction = await client.waitForFinalization({ hash: txId });
  if (!isSuccessful(transaction)) {
    throw new Error(`Deployment failed: ${transaction.statusName} / ${transaction.txExecutionResultName}`);
  }
  const decoded = transaction.txDataDecoded as DecodedDeployData | undefined;
  const contractAddress = decoded?.contractAddress ?? transaction.recipient;
  if (!contractAddress) throw new Error('Finalized deployment has no contract address');
  return contractAddress;
}
```
`initializeConsensusSmartContract()` is **deprecated** on the v2 client. A later script must wait for and
verify the prior tx outcome rather than assuming an address exists.

### 6.3 `genlayer-py` client (`pip install genlayer-py`)

```python
from genlayer_py import create_account, create_client
from genlayer_py.chains import localnet

client = create_client(chain=localnet, account=create_account())

value = client.read_contract(address=addr, function_name="get_storage", args=[])

estimate = client.estimate_transaction_fees({
    "leaderTimeunitsAllocation": 125, "validatorTimeunitsAllocation": 250,
    "executionBudgetPerRound": 786_500, "totalMessageFees": 0,
    "appealRounds": 1, "rotations": [1, 1],
})
tx_id = client.write_contract(
    address=addr, function_name="update_storage", args=["new value"],
    fees={"distribution": estimate["distribution"], "feeValue": estimate["feeValue"]},
)

from genlayer_py.transactions import is_successful
receipt = client.wait_for_finalization(tx_id)
if not is_successful(receipt):
    raise RuntimeError(f"{receipt['status_name']} / {receipt['tx_execution_result_name']}")

charge = client.get_appeal_charge(tx_id)
client.appeal_transaction(tx_id, value=charge)
```

Key signatures:
```python
client.deploy_contract(code, account=None, args=None, kwargs=None,
                       consensus_max_rotations=None, leader_only=False,
                       sim_config=None, valid_until=None, fees=None)
client.write_contract(address, function_name, account=None, consensus_max_rotations=None,
                       value=0, leader_only=False, args=None, kwargs=None,
                       sim_config=None, valid_until=None, fees=None)
client.read_contract(address, function_name, args=None, kwargs=None, account=None,
                     raw_return=False,
                     transaction_hash_variant=TransactionHashVariant.LATEST_NONFINAL,
                     sim_config=None)
client.wait_for_decision(transaction_hash, interval=3000, retries=10, full_transaction=False)
client.wait_for_finalization(transaction_hash, interval=3000, retries=10, full_transaction=False)
client.get_transaction(transaction_hash)
client.get_transaction_lifecycle(transaction_hash, timestamp=None)
client.can_appeal(transaction_id, expected_decision_id=None)
client.get_appeal_quote(transaction_id) -> Dict     # decision id, charges, deadline
client.get_min_appeal_bond(transaction_id) -> int   # DEPRECATED alias of get_appeal_charge
client.top_up_fees(transaction_id, distribution, value, account=None)
client.get_contract_schema(address)                 # localnet only
client.get_contract_schema_for_code(contract_code)  # localnet only
client.simulate_write_contract(...)                 # localnet only
client.fund_account(address, amount)                # localnet only
client.debug_trace_transaction(transaction_hash, round=0)
```

Status enum (mirrors genlayer-js `TransactionStatus`):
`UNINITIALIZED, PENDING, PROPOSING, COMMITTING, REVEALING, ACCEPTED, UNDETERMINED, FINALIZED,
CANCELED, APPEAL_REVEALING, APPEAL_COMMITTING, READY_TO_FINALIZE, VALIDATORS_TIMEOUT, LEADER_TIMEOUT`.

`TransactionResult`: `IDLE, AGREE, DISAGREE, TIMEOUT, DETERMINISTIC_VIOLATION, NO_MAJORITY,
MAJORITY_AGREE, MAJORITY_DISAGREE, MAJORITY_TIMEOUT`.
`ExecutionResult` / `VoteType`: `NOT_VOTED, FINISHED_WITH_RETURN, FINISHED_WITH_ERROR, TIMEOUT,
NONDET_DISAGREE, DETERMINISTIC_VIOLATION`.

---

## 7. Consensus authoring rules (the part that actually decides success)

1. **`gl.nondet.*` calls must be inside a nondet block.** Storage writes, `gl.contract.get_at`,
   `.emit()`, and nested nondet blocks must be **outside**.
2. **Do not trust the leader.** A validator that only checks the leader's JSON shape / enum range /
   non-empty summary is *not* consensus. Re-run the task, or judge against the same source data.
3. **`strict_eq` only for canonicalizable output.** LLM text and raw web content will never agree.
   Canonicalize (`json.dumps(..., sort_keys=True)`) or use a custom validator.
4. **Extract stable web fields.** Return `id/title/state`, not `updated_at/followers/reactions`.
5. **Compare derived status**, not raw arrays, when even stable fields can drift.
6. **Always `response_format="json"`**, then validate structure and types anyway.
7. **Ground LLM judgment with programmatic facts**: generate checkable expressions → `eval` them in
   `gl.vm.spawn_sandbox` → inject results as ground truth.
8. **Classify errors** so consensus retries instead of locking in bad state:
   `[EXPECTED]`/`[EXTERNAL]` must match exactly; `[TRANSIENT]` both-transient ⇒ agree; LLM errors ⇒ always disagree.
9. **Scaled integers don't enforce ranges in expressions** — `u256(a) + u256(b)` is plain `a + b`.
   Checks fire on storage assignment only.

### Validator error-classification pattern (SDK-correct)
```python
def _handle_leader_error(leaders_res, leader_fn) -> bool:
    leader_msg = leaders_res.message if isinstance(leaders_res, gl.vm.VMError) else None
    try:
        leader_fn()
        return False                       # leader errored, we succeeded -> disagree
    except gl.vm.UserError as e:
        if leader_msg is not None:
            return False                   # mismatched error kinds
        return False
    except Exception:
        return False
```
Use `e.data` for `UserError`, `e.message` for `VMError`. The SDK's own default comparison is
`a.data == b.data`.

---

## 8. Contract skeletons

Storage:
```python
class Storage(gl.contract.Contract):
    storage: str
    def __init__(self, initial_storage: str):
        self.storage = initial_storage
    @gl.public.view
    def get_storage(self) -> str:
        return self.storage
    @gl.public.write
    def update_storage(self, new_storage: str) -> None:
        self.storage = new_storage
```

Strict-equality web fetch:
```python
@gl.public.write
def had_iana(self) -> None:
    def leader_fn():
        return 'iana' in gl.nondet.web.render("https://example.org", mode='html')
    self.result = gl.eq_principle.strict_eq(leader_fn)
```

Custom leader/validator with numeric tolerance (SDK-correct name):
```python
@gl.public.write
def update_price(self, pair: str) -> None:
    def leader_fn():
        return json.loads(gl.nondet.web.get(self.url(pair)).body.decode("utf-8"))["price"]

    def validator_fn(leader_result) -> bool:
        if not isinstance(leader_result, gl.vm.Return):
            return False
        leader_price = leader_result.calldata
        validator_price = leader_fn()
        if leader_price == 0:
            return validator_price == 0
        return abs(leader_price - validator_price) / abs(leader_price) <= 0.02

    self.prices[pair] = gl.vm.run_nondet(leader_fn, validator_fn)   # was run_nondet_unsafe in docs
```

LLM + images:
```python
def leader_fn():
    return gl.nondet.exec_prompt(
        f"Does this receipt show {expected}? Respond as JSON: {{\"matches\": true/false}}",
        images=[image_bytes], response_format="json",     # max 2 images
    )

def validator_fn(leader_result) -> bool:
    if not isinstance(leader_result, gl.vm.Return):
        return False
    return leader_fn()["matches"] == leader_result.calldata["matches"]

result = gl.vm.run_nondet(leader_fn, validator_fn)
```

Value transfers:
```python
@gl.public.write.payable
def tip(self) -> None:
    v = gl.message.value
    if v == u256(0):
        raise gl.vm.UserError("send some value")
    self.total_tips += v

other = gl.contract.get_at(addr)
other.emit_transfer(value=u256(amount), on='finalized')
other.emit(value=u256(amount), on='finalized').deposit()   # recipient must be .payable
```

---

## 9. Environment notes

- Python **3.12+** for `genlayer-test`.
- Debugging: `print()` → node/Studio stdout; `gl.trace(...)` → genvm_log with timestamps.
  Attaching a real debugger is **not supported**.
- Time is the **transaction** datetime — use it for relative arithmetic and audit trails,
  never for "what time is it right now".
- No block number/hash/gas/nonce in contract context. Fetch block height via web access in a nondet block.
- GEN is the native token; 1 GEN = 10^18 wei; amounts are `u256`.
- Ghost contracts back every IC on chain (same address) and hold the IC's GEN balance.
  **Ghost contracts are not implemented in Studio** — balances live in a local DB there.
- Image processing needs a vision-capable model on the validators.