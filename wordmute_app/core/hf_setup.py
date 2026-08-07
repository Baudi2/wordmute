"""Hugging Face onboarding for GigaAM.

GigaAM's long-audio pipeline depends on the gated pyannote
segmentation model, which requires each user's own free Hugging Face
account, an access token, and a one-time consent form on the model
page — none of which can be automated or bundled. This module validates
that a pasted token works and that the consent step was completed.
huggingface_hub is imported lazily (it ships with the ASR stack)."""

GATED_MODEL = "pyannote/segmentation-3.0"
TOKEN_URL = "https://huggingface.co/settings/tokens"
CONSENT_URL = f"https://huggingface.co/{GATED_MODEL}"
SIGNUP_URL = "https://huggingface.co/join"


class SetupError(Exception):
    """Validation failure with a user-facing message."""


def validate_token(token: str) -> str:
    """Check the token against Hugging Face; returns the account name."""
    token = token.strip()
    if not token:
        raise SetupError("Paste your Hugging Face access token first.")
    try:
        import huggingface_hub
    except ImportError:
        raise SetupError(
            "The huggingface_hub package is not installed — it comes with "
            "the GigaAM/whisper dependencies.") from None
    try:
        info = huggingface_hub.HfApi().whoami(token=token)
    except Exception as exc:
        raise SetupError(
            f"Hugging Face rejected the token ({exc}). Create a 'read' "
            f"token at {TOKEN_URL} and paste it exactly.") from None
    return info.get("name") or info.get("fullname") or "unknown"


def check_pyannote_access(token: str) -> None:
    """Verify the account has accepted the gated pyannote model's terms."""
    import huggingface_hub
    auth_check = getattr(huggingface_hub, "auth_check", None)
    try:
        if auth_check is not None:
            auth_check(GATED_MODEL, token=token)
        else:  # older huggingface_hub: probing a tiny file works the same
            huggingface_hub.hf_hub_download(GATED_MODEL, "config.yaml",
                                            token=token)
    except Exception as exc:
        if "Gated" in type(exc).__name__:
            raise SetupError(
                f"Your account has not been granted access to {GATED_MODEL} "
                f"yet. Open {CONSENT_URL}, fill in the short access form, "
                "then validate again.") from None
        raise SetupError(
            f"Could not verify access to {GATED_MODEL}: {exc}") from None
