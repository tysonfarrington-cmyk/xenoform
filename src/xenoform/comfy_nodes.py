"""ComfyUI nodes. They import without ComfyUI installed, so a smoke test can register them."""

from __future__ import annotations

import os


class XenoformTryIt:
    """One click. Bundled demo, Pynchon register, dry-run draft or final."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "quality": (["live", "turbo", "draft", "final"], {"default": "turbo"}),
                "register": (["pynchon", "lecarre", "tolkien", "rome"], {"default": "pynchon"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "go"
    CATEGORY = "Xenoform"
    OUTPUT_NODE = True
    DESCRIPTION = "Render the bundled royalty-free demo with the chosen register. No model is required for the dry run."

    def go(self, quality="draft", register="pynchon"):
        from xenoform.errors import PlainError, plain_error
        from xenoform.try_it import try_demo

        try:
            result = try_demo(quality=quality, register=register, tiny=os.environ.get("XENO_TINY") == "1")
        except PlainError as exc:
            raise PlainError(str(exc)) from exc
        except Exception as exc:
            raise PlainError(plain_error(exc)) from exc
        text = result["message"]
        return {"ui": {"text": [text]}, "result": (text,)}


class XenoformSetup:
    """Report missing weights. The desk's Setup screen does the download."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "report"
    CATEGORY = "Xenoform"
    OUTPUT_NODE = True
    DESCRIPTION = "Say which models are missing, and which hardware tier this machine landed on."

    def report(self):
        from xenoform.models_setup import inspect_setup

        setup = inspect_setup()
        missing = setup["missing_required"]
        if missing:
            text = f"Still to install: {', '.join(missing)}. Open the Xenoform tab and use Setup. Tier: {setup['tier']['label']}."
        else:
            text = f"The fast model is installed. Tier: {setup['tier']['label']}."
        return {"ui": {"text": [text]}, "result": (text,)}


NODE_CLASS_MAPPINGS = {
    "XenoformTryIt": XenoformTryIt,
    "XenoformSetup": XenoformSetup,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XenoformTryIt": "Xenoform Try It",
    "XenoformSetup": "Xenoform Setup Check",
}
