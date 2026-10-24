from strands.models.bedrock import BedrockModel

# Centralized model id for the Sales agent.
# Claude Sonnet 4.6 — reliable instruction-following for handoff/discount/OTP logic.
# Served via a `global.` cross-Region inference profile on Bedrock. Confirm the
# exact profile id for your account/region at deploy time
# (e.g. `aws bedrock list-inference-profiles`), then update MODEL_ID here.
MODEL_ID = "global.anthropic.claude-sonnet-4-6"


def load_model() -> BedrockModel:
    """Get the Bedrock model client for Sales using IAM credentials."""
    return BedrockModel(model_id=MODEL_ID)
