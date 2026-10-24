# Acme Telco — AgentCore Project

This project is a prototype of two Amazon Bedrock AgentCore agents for the fictitious
**Acme Telco**: a **Customer Service** agent (plan/subscription Q&A) and a **Sales** agent
(re-contracting, device discounts with human-in-the-loop approval, and email OTP before an order).

The `agentcore/` directory is the declarative model of the project. `agentcore.json` is the source of
truth; `agentcore validate` checks it against the schema in `agentcore/.llm-context/`.

## Mental Model

- Flat resource model: runtimes, memories, gateways, etc. are independent top-level arrays in
  `agentcore.json`. Agents discover memory/config at runtime via environment variables.
- Two runtimes: `AcmeCustomerService` and `AcmeSales`. Customer Service hands off to Sales via the
  `acme-sales-gateway` `httpRuntime` target (agent-as-tool over HTTP runtime).
- Two identity layers: the **JWT** authorizes the runtime call (mock locally, Cognito deployed); the
  **Acme customer** (Alice/Bob) is resolved in-chat by mobile/account number and confirmed by OTP.

## Critical Invariants

1. Schema-first: `.json` files are the source of truth; do not hand-edit generated CDK.
2. Resource identity: the `name` field is the CloudFormation Logical ID. Renaming destroys+recreates;
   other field changes update in place.
3. `httpRuntime` gateway targets require the gateway `protocolType: "None"`.
4. Validate with `agentcore validate` after every config change.
5. Invocation input: require the `prompt` to be a non-empty string (both entrypoints enforce this).

## Directory Structure

```
AcmeCustomerService/
├── AGENTS.md
├── README.md
├── agentcore/
│   ├── agentcore.json        # two runtimes + SharedMemory + sales gateway + CUSTOM_JWT placeholders
│   ├── aws-targets.json      # account + region (placeholders)
│   └── .llm-context/         # READ-ONLY schema types for validation
├── app/
│   ├── AcmeCustomerService/  # Nova Lite runtime: plan Q&A, identify_customer, handoff_to_sales
│   │   ├── main.py, tools.py, handoff.py, auth_local.py
│   │   ├── model/load.py, memory/session.py
│   │   ├── data/plans.py, data/customers.py
│   │   └── frontend/         # Flask landing + chat
│   ├── AcmeSales/            # Sonnet 4.5 runtime: eligibility, offers, HITL approval, OTP
│   │   ├── main.py, tools.py, sales_logic.py, auth_local.py
│   │   ├── model/load.py, memory/session.py
│   │   ├── data/devices.py, hitl/store.py, otp/verify.py
│   ├── ApprovalConsole/      # Flask manager-approval console (Mr Anwar)
│   └── auth/                 # mock JWT helper (shared reference copy)
├── scripts/demo_e2e.py       # end-to-end business-logic demo
└── tests/                    # pytest suite
```

## Models

- `AcmeCustomerService` → Amazon Nova Lite (`app/AcmeCustomerService/model/load.py`).
- `AcmeSales` → Claude Sonnet 4.6 via a `global.` inference profile (`app/AcmeSales/model/load.py`).
- Model ids are single constants; confirm the exact Bedrock inference-profile id for your account/region
  at deploy time (`aws bedrock list-inference-profiles`).

## CLI

```bash
agentcore validate     # validate agentcore.json
agentcore dev          # run runtimes locally with hot-reload
agentcore invoke       # invoke a runtime (local or deployed)
agentcore deploy       # deploy to AWS
agentcore status       # deployment status
agentcore remove <r>   # remove a resource, then `agentcore deploy` to tear down
```
