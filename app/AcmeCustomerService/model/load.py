from strands.models.bedrock import BedrockModel

# Centralized model id for the Customer Service agent.
# Amazon Nova Lite — cheap and capable for simple, tool-driven Q&A.
# Switch to another Bedrock model/inference-profile id here if needed.
MODEL_ID = "us.amazon.nova-lite-v1:0"


def load_model() -> BedrockModel:
    """Get the Bedrock model client for Customer Service using IAM credentials."""
    return BedrockModel(model_id=MODEL_ID)
