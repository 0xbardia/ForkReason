# GenLayer Contract Testing — Current Reference (Direct Mode + Studio Mode)

Compiled 2026-10-03 from the live docs (`docs.genlayer.com`), the `genlayer-testing-suite`
source (v0.29.2, the package that publishes as `gltest`), `genlayer-py`, and the
`genlayer-project-boilerplate` CI. Command truth was cross-checked against the
**installed** `genlayer` CLI **0.40.0-rc.3** in this environment.

---

## 0. TL;DR — pick the mode, run the command

| You want | Mode | Docker? | Exact command |
|---|---|---|---|
| Unit tests, storage/views/writes, reverts, mocks | **Direct** | No | `pytest tests/direct/ -v` |
| Consensus logic of the equivalence principle (leader vs validator) | **Direct** (`run_validator`) | No | `pytest tests/direct/ -v -k consensus` |
| Multi-validator consensus over JSON-RPC, fast | **Studio Mode + GLSim** | **No** | `glsim --port 4000 --validators 5` then `gltest tests/integration/ -v -s` |
| Multi-validator consensus in the **real GenVM runtime** | **Studio Mode + local Studio** | **Yes** | `genlayer init && genlayer up` then `gltest tests/integration/ -v -s --network localnet` |
| Hosted consensus, no local infra | **Studio Mode + studionet** | No | `gltest tests/integration/ -v -s --network studionet` |
| Pre-production | **Studio Mode + testnet** | No | `gltest tests/integration/ -v -s --network testnet_bradbury` |

> **Direct Mode and GLSim do NOT require Docker.** Docs, verbatim
> (`/developers/intelligent-contracts/tooling-setup`, `last_updated: 2026-09-03`):
> *"Docker is only required if you want to run GenLayer Studio locally. Direct mode
> tests and GLSim work without Docker."*

Install (both modes come from one package):

```bash
pip install genlayer-test          # import name is `gltest`  (current: 0.29.2)
pip install genlayer-test[sim]      # adds `glsim` (needs `sim` extra!)
```

Requires Python **>= 3.12** (upstream CI matrix: 3.12, 3.13).

---

## 1. Direct Mode — no Docker, no network

### Run

```bash
pytest tests/ -v                       # whole suite
pytest tests/direct/ -v                # only direct tests
pytest tests/direct/test_views.py -v   # one file
pytest tests/direct/ -v -k test_revert # by name
pytest tests/direct/ -v -m direct      # by marker (auto-applied, see below)
pytest tests/direct/ -v -x             # stop on first failure
```

`gltest tests/direct/ -v` also works — `gltest` *is* `pytest.main()` with two extra
plugins auto-registered (see §4). Plain `pytest` is the documented Direct Mode runner.

### Fixtures (auto-injected by the `gltest_direct` pytest plugin)

| Fixture | Meaning |
|---|---|
| `direct_vm` | `VMContext`, already activated, with cheatcodes |
| `direct_deploy(path, *args, sdk_version=None, **kwargs)` | deploys a contract in-memory and returns the instance |
| `direct_alice`, `direct_bob`, `direct_charlie` | named test addresses |
| `direct_owner` | the default sender |
| `direct_accounts` | list of 10 addresses |

`direct_deploy` resolves relative paths against cwd, `contracts/`, then
`intelligent-contracts/`. Tests using `direct_vm`/`direct_deploy` are **auto-marked**
`@pytest.mark.direct` by the plugin, so `-m direct` / `-m "not direct"` work with no
decorator.

### Cheatcode surface (from `gltest/direct/pytest_plugin.py` + API reference)

```python
direct_vm.sender = alice                      # persistent sender
with direct_vm.prank(bob): ...                # one-call sender swap
with direct_vm.expect_revert("Unauthorized"):  # substring match; no arg = any error
    contract.owner_action()

snap = direct_vm.snapshot()                   # full state: storage+mocks+sender+validators
contract.increment()
direct_vm.revert(snap)                        # state fully restored

direct_vm.mock_web(r"api\.example\.com/price", {"status": 200, "body": '{"p":42}'})
direct_vm.mock_llm(r"(?s).*", '{"verdict": "true"}')   # regex over prompt text
direct_vm.clear_mocks()

direct_vm.strict_mocks = True                 # error on any mock never matched
direct_vm.check_pickling = True               # validate nondet closures (WASM boundary parity)
direct_vm.warp("2024-01-01T00:00:00Z")        # ISO timestamp; patches datetime.now()
direct_vm.deal(addr, 1000)
direct_vm.startPrank(addr) / direct_vm.stopPrank()
```

### Consensus testing WITHOUT a network (the high-value bit)

```python
def test_consensus(direct_vm, direct_deploy):
    direct_vm.mock_llm(r".*", '{"verdict": "true"}')
    c = direct_deploy("contracts/FactChecker.py")
    c.check_claim("The sky is blue")     # leader runs, validator_fn captured internally

    direct_vm.clear_mocks()             # validator now sees different data
    direct_vm.mock_llm(r".*", '{"verdict": "false"}')
    assert direct_vm.run_validator() is False   # semantic disagreement -> UNDETERMINED
```

`vm.run_validator(leader_result=..., leader_error=..., index=-1)` returns the validator's
bool; `-1` = most recent `gl.vm.run_nondet` capture. Use `(?s).*` for leader prompts —
multiline rule text means `.` alone will not match the whole prompt.

Programmatic (non-pytest) entry points, if you want a bespoke harness:

```python
from gltest.direct import VMContext, deploy_contract, create_address   # fixtures live here
from gltest.direct.loader import load_contract_class

vm = VMContext(); vm.strict_mocks = True; vm.check_pickling = True
vm.sender = create_address("owner")        # MUST be set before activate()
with vm.activate():
    c = deploy_contract(Path("contracts/C.py"), vm)
```

Two hard-won gotchas (validate locally before you trust a green run): set
`vm.sender` **before** `activate()`, or the constructor sees
`gl.message.sender_address is None` and dies deep inside storage init; and
`load_contract_class` may only be called **once per process** per file (second call
raises `only one contract is allowed`).

### Optional extra gate before tests

```bash
genvm-lint check contracts/MyContract.py     # AST + SDK-reflection validation
GENVM_VERSION=v0.3.0-rc7 genvm-lint check contracts/MyContract.py   # if SDK bundle hash is unresolved
```

---

## 2. Studio Mode — via JSON-RPC

Studio Mode = the same `gltest` runner talking to a network RPC. **Four backends**;
pick one:

### 2a. GLSim — local, Docker-free (recommended for this box)

Single-process GenLayer network that runs contracts through the Direct runner natively
(no WASM/GenVM), supports real LLM + web I/O, mocks, snapshots and time travel.

```bash
pip install genlayer-test[sim]
glsim --port 4000 --validators 5            # start (chain-id 61127, max-rotations 3)
gltest tests/integration/ -v -s             # in another shell; default network=localnet
```

| flag | default | notes |
|---|---|---|
| `--port` | `4000` | matches `gltest`'s default localnet URL |
| `--host` | `127.0.0.1` | |
| `--validators` | `5` | **this is your validator count** |
| `--max-rotations` | `3` | |
| `--chain-id` | `61127` | |
| `--llm-provider` | none | e.g. `openai:gpt-4o` (real LLM instead of mocks) |
| `--no-browser` | false | use httpx instead of Playwright for web calls |
| `--seed` | none | deterministic addresses |
| `-v, --verbose` | false | |

JSON-RPC at `POST /api`: `gen_call`, `gen_get_contract_schema`,
`gen_get_transaction_status`, plus `sim_deploy`, `sim_call`, `sim_read`,
`sim_fund_account`, `sim_get_balance`, `sim_create_snapshot`, `sim_restore_snapshot`,
`sim_install_mocks`, `sim_get_mocks`, `sim_increase_time`, `sim_set_time`, and the
Ethereum-compatible `eth_*` set.

Caveat from the docs: *"GLSim runs the Python runner natively — not inside GenVM — so
there can be minor incompatibilities with the full runtime. Use it for fast development
cycles, then validate against Studio before deploying."* It is the correct tool for
multi-validator consensus logic, not for final runtime certification.

### 2b. Local GenLayer Studio — real GenVM, **requires Docker 26+**

```bash
npm install -g genlayer      # Node 18+; on Linux also: apt-get install libsecret-1-0
genlayer init                # one-time: download localnet, create validators
genlayer up                  # start localnet + Studio UI
# UI:      http://localhost:8080
# RPC:     http://127.0.0.1:4000/api   <- what gltest hits
gltest tests/integration/ -v -s --network localnet
genlayer stop
```

`genlayer init [options]`

| flag | default |
|---|---|
| `--numValidators <n>` | `5` |
| `--headless` | `false` |
| `--reset-db` | `false` |
| `--localnet-version <v>` | `v0.65.0` (minimum) |
| `--ollama` | `false` |

`genlayer up [options]`

| flag | default |
|---|---|
| `--reset-validators` | `false` (recreate random validators) |
| `--numValidators <n>` | `5` |
| `--headless` | `false` |
| `--reset-db` | `false` |
| `--ollama` | `false` |

Both verified verbatim against the installed CLI 0.40.0-rc.3 (`genlayer up --help`).

Validator management while Studio is up:

```bash
genlayer localnet validators get
genlayer localnet validators count
genlayer localnet validators create-random --count 3 --providers openai ollama --models gpt-4o
genlayer localnet validators delete --address 0x…
```

### 2c. Hosted studionet — no Docker, no local infra

```bash
gltest tests/integration/ -v -s --network studionet
```

RPC `https://studio.genlayer.com/api`. Accounts are auto-generated per run. Rate
limited vs local Studio (~30 req/min for reads).

### 2d. Testnet

```bash
gltest tests/integration/ -v -s --network testnet_bradbury     # or testnet_asimov
```

Requires `accounts:` (private keys) in `gltest.config.yaml`; `testnet_*` ships with
`accounts=None` and the plugin hard-exits (`gltest configuration error`) without them.
`match_std_out` / `match_std_err` assertions are **localnet/studionet only**.

### Studio Mode test API

```python
from gltest import get_contract_factory, get_default_account, get_validator_factory
from gltest.assertions import tx_execution_succeeded, tx_execution_failed
from gltest.types import MockedLLMResponse, MockedWebResponse

factory = get_contract_factory("Storage")            # by artifact name
factory = get_contract_factory(contract_file_path="contracts/Storage.py")  # or by path
contract = factory.deploy(args=["init"], account=get_default_account(),
                          consensus_max_rotations=3)  # -> Contract instance
receipt  = factory.deploy_contract_tx(args=["init"])  # -> receipt only
contract = factory.build_contract("0x…")             # bind existing address

contract.get_storage().call()                        # reads -> value directly
contract.update_storage(args=["new"]).transact(
    value=0, consensus_max_rotations=3,
    wait_interval=1000, wait_retries=10)             # writes -> receipt
assert tx_execution_succeeded(receipt)
tx_execution_succeeded(receipt, match_std_out=r".*code \d+")
```

Fixtures: `gl_client`, `default_account`, `accounts` (all session-scoped).

Multi-validator with **mock validators** (deterministic; no provider keys):

```python
mock_llm: MockedLLMResponse = {
    "nondet_exec_prompt":               {"analyze this": "positive sentiment"},
    "eq_principle_prompt_comparative":  {"values match": True},
    "eq_principle_prompt_non_comparative": {},
}
mock_web: MockedWebResponse = {
    "nondet_web_request": {
        "https://api.example.com/price": {"method": "GET", "status": 200,
                                          "body": json.dumps({"price": 100.50})},
    }
}
vf = get_validator_factory()
validators = vf.batch_create_mock_validators(count=5,
                                              mock_llm_response=mock_llm,
                                              mock_web_response=mock_web)
ctx = {"validators": [v.to_dict() for v in validators],
       "genvm_datetime": "2024-01-01T00:00:00Z"}
contract = factory.deploy(transaction_context=ctx)
receipt = contract.analyze_text(args=["analyze this"]).transact(transaction_context=ctx)
```

Mock keys map to `gl.nondet.exec_prompt`, `gl.eq_principle.prompt_comparative`,
`gl.eq_principle.prompt_non_comparative`. Matching is **substring** on the internal
user message (LLM) and **exact URL incl. query string** (web). Real validators:

```python
vf.batch_create_validators(count=5, stake=10, provider="openai", model="gpt-4o",
                           config={"temperature": 0.7}, plugin="openai-compatible",
                           plugin_config={"api_key_env_var": "OPENAI_API_KEY"})
```

Statistical consensus sweep (LLM contracts):

```python
a = contract.process_with_llm(args=["input"]).analyze(provider="openai", model="gpt-4o", runs=100)
print(a.success_rate, a.reliability_score, a.unique_states)
```

---

## 3. `gltest.config.yaml` (optional; project root)

```yaml
networks:
  default: localnet
  localnet:
    url: "http://127.0.0.1:4000/api"
    leader_only: false
  studionet: {}                       # preconfigured; accounts auto-generated
  testnet_asimov:
    accounts: ["${ACCOUNT_PRIVATE_KEY_1}", "${ACCOUNT_PRIVATE_KEY_2}"]
    from: "${ACCOUNT_PRIVATE_KEY_1}"
paths:
  contracts: "contracts"
  artifacts: "artifacts"
environment: .env                      # ${VAR} interpolation comes from here
```

Valid per-network keys: `id, url, accounts, from, leader_only, default_wait_interval,
default_wait_retries, chain_type`. Custom (non-preconfigured) networks **require**
`id`, `url`, `accounts`, `chain_type`. Defaults with no config file (source:
`gltest_cli/config/constants.py`): network `localnet`, RPC `http://127.0.0.1:4000/api`,
chain-id `61999` (from `genlayer_py.chains.localnet`), contracts `contracts/`,
artifacts `artifacts/`, env `.env`, `wait_interval=3000` ms, `wait_retries=50`,
`leader_only=False`, 10 auto-generated accounts, console paths
`contracts/` + `intelligent-contracts/`.

---

## 4. Exact `gltest` CLI flags (authoritative — from `gltest_cli/config/plugin.py`)

`gltest` is literally `pytest.main()`, so **every pytest flag passes through**
(`-v`, `-vv`, `-k`, `-m`, `-x`, `--maxfail`, `--tb=short`, node ids,
`tests/test_x.py::TestY::test_z`, `-s`, `-q`). On top of that the `gltest` plugin adds:

| Flag | Type | Effect |
|---|---|---|
| `--network <name>` | store | `localnet` (default), `studionet`, `testnet_asimov`, `testnet_bradbury` |
| `--rpc-url <url>` | store | override RPC endpoint |
| `--chain-type <t>` | store | override chain type (`localnet`, `studionet`, `testnet_asimov`, `testnet_bradbury`) |
| `--contracts-dir <path>` | store | contract directory (default `contracts/`) |
| `--artifacts-dir <path>` | store | artifacts dir (wiped at session start) |
| `--default-wait-interval <ms>` | store | receipt poll interval (default 3000) |
| `--default-wait-retries <n>` | store | receipt retries (default 50) |
| `--leader-only` | flag | skip consensus on all deploys/writes. **Only has an effect on studio-based RPCs** (localhost, 127.0.0.1, `*.genlayer.com`, `*.genlayerlabs.com`); elsewhere it logs a warning and does nothing |

Two pytest plugins autoload via `pytest11` entry points: `gltest`
(`gltest_cli.config.plugin` — Studio/network/config) and `gltest_direct`
(`gltest.direct.pytest_plugin` — Direct fixtures + `direct` marker).

---

## 5. CI recipes

### Direct Mode only (what upstream ships) — no infra

`genlayer-project-boilerplate/.github/workflows/ci.yml`, verbatim:

```yaml
  test-direct:
    name: Direct Mode Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest tests/direct/ -v
```

Its `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: tests requiring GenLayer Studio (run with gltest)"]
```

### The suite's own CI — `genlayer-testing-suite/.github/workflows/tests.yml`

```yaml
    strategy:
      matrix:
        python-version: [3.12, 3.13]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install ${{ matrix.python-version }}
      - run: uv sync --extra sim --python ${{ matrix.python-version }}
      - run: uv run gltest tests/gltest_cli/
      - run: uv run gltest tests/gltest/
      - run: uv run gltest tests/glsim/
      # Unit tests only — integration tests here download the GenVM SDK.
      - run: uv run gltest tests/gltest_direct/test_sdk_loader.py
```

(`uv run gltest …` works because the project installs itself into the venv.)

### Adding a Studio-Mode job

GLSim, no Docker — the cheapest real consensus coverage:

```yaml
  integration-glsim:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt          # includes genlayer-test[sim]
      - run: |
          glsim --port 4000 --validators 5 --seed ci > glsim.log 2>&1 &
          for i in $(seq 1 30); do
            curl -sf -X POST http://127.0.0.1:4000/api -H 'Content-Type: application/json' \
              -d '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' && break
            sleep 1
          done
      - run: gltest tests/integration/ -v -s --network localnet
      - if: failure()
        run: cat glsim.log
```

Local Studio (full GenVM consensus) — needs Docker:

```yaml
      - run: npm install -g genlayer
      - run: genlayer init --headless
      - run: genlayer up --headless          # Docker daemon must be up on the runner
      - run: gltest tests/integration/ -v -s --network localnet
```

Notes that bite in CI: give Studio generous startup time before `gltest`; keep
`--leader-only` out of consensus CI (it disables consensus on studio-based RPCs);
`match_std_*` assertions don't exist on testnet; artifacts dir is wiped at session
start, so write evidence elsewhere.

---

## 6. Obsolete — do not use

| Command | Status |
|---|---|
| `genlayer studio up` | **Gone.** Current CLI has no `studio` subcommand (verified on installed 0.40.0-rc.3: only `init`, `up`, `stop`, `localnet`, …). |
| `genlayer-test-genlayer studio up` | **Gone.** That binary belonged to the old `genlayer-test` distribution, superseded by the `genlayer-test` package / `gltest` CLI. |
| `pytest` for Studio Mode | Works only incidentally (both plugins autoload); the documented runner is `gltest`. |

---

## 7. Status in THIS environment (verified)

- **Docker is unavailable.** `docker`, `podman`, `nerdctl` all absent; no
  `/var/run/docker.sock`. → **Local Studio Mode (`genlayer up`, full GenVM consensus)
  cannot run here.** `genlayer init`/`genlayer up` would fail at the Docker step.
- `genlayer` CLI **0.40.0-rc.3** is installed (npm), but `genlayer-test` / `gltest` /
  `glsim` are **not installed**; PyPI currently serves `genlayer-test 0.29.2`.
- Only **Python 3.14.7** is present; upstream targets/tests 3.12 and 3.13, so pin a
  3.12/3.13 interpreter for a reproducible suite.
- **Therefore, what actually works here:** Direct Mode (`pip install genlayer-test` in a
  3.12/3.13 venv, then `pytest tests/direct/ -v`) and GLSim-backed Studio Mode
  (`pip install genlayer-test[sim]`, `glsim …`, `gltest …`) — neither needs Docker.
  Hosted studionet (`--network studionet`) also needs no Docker but needs outbound
  network access.

---

## 8. Sources

- `docs.genlayer.com/developers/intelligent-contracts/testing` (`last_updated 2026-06-11`)
- `docs.genlayer.com/api-references/genlayer-test` (2026-03-27), `/direct` (2026-04-20),
  `/integration` (2026-03-27), `/glsim` (2026-03-27)
- `docs.genlayer.com/developers/intelligent-contracts/tooling-setup` (2026-09-03)
- `docs.genlayer.com/api-references/genlayer-cli` (2026-09-03) + `/environment/{init,up,stop}`
- `github.com/genlayerlabs/genlayer-testing-suite` @ `main` — `pyproject.toml` (v0.29.2),
  `gltest_cli/main.py`, `gltest_cli/config/plugin.py`, `gltest_cli/config/constants.py`,
  `gltest_cli/config/user.py`, `gltest/direct/pytest_plugin.py`, `docs/studio-runner.md`,
  `docs/direct-runner.md`, `.github/workflows/tests.yml`, `tests/glsim/test_consensus.py`
- `github.com/genlayerlabs/genlayer-py` — `genlayer_py/chains/{localnet,studionet}.py`
- `github.com/genlayerlabs/genlayer-project-boilerplate` — `.github/workflows/ci.yml`,
  `gltest.config.yaml`, `requirements.txt`, `pyproject.toml`, `tests/{direct,integration}`
- Tip: any docs page has a raw-markdown twin — append `.md` to the URL
  (e.g. `https://docs.genlayer.com/developers/intelligent-contracts/testing.md`); the
  full map is at `https://docs.genlayer.com/llms.txt`.