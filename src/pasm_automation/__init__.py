"""Python bindings for the emulator automation C ABI."""

from .ctypes_api import (
    EMU_AUTOMATION_ABI_VERSION,
    AutomationError,
    AutomationLibrary,
    Capabilities,
    FrameMetadata,
    FramebufferSnapshot,
    Machine,
    MachineDescriptor,
    Rect,
    TextCell,
    TextGridSnapshot,
    TextViewDescriptor,
)

__all__ = [
    "EMU_AUTOMATION_ABI_VERSION",
    "AutomationError",
    "AutomationLibrary",
    "Capabilities",
    "FrameMetadata",
    "FramebufferSnapshot",
    "Machine",
    "MachineDescriptor",
    "Rect",
    "TextCell",
    "TextGridSnapshot",
    "TextViewDescriptor",
]
