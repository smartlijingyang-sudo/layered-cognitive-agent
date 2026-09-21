from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.profile.profile import DEFAULT_PROFILE
from lca.infrastructure.cli.services.kernel.supervisor import default_program_config


def test_default_program_config_uses_web_assistant():
    cfg = default_program_config()
    assert "--profile" in cfg.args
    idx = cfg.args.index("--profile")
    assert cfg.args[idx + 1] == "profiles/web-assistant.yaml"


def test_default_profile_constant_is_web_assistant():
    assert DEFAULT_PROFILE == "profiles/web-assistant.yaml"


def test_kernel_serve_config_default_profile_is_web_assistant():
    cfg = KernelServeConfig()
    assert cfg.profile == "profiles/web-assistant.yaml"
