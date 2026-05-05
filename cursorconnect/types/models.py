from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union


class CommonModels:
    """A registry of common model IDs for convenient autocomplete."""
    DEFAULT = "default"
    COMPOSER_2 = "composer-2"
    COMPOSER_1_5 = "composer-1.5"
    
    GPT_5_5 = "gpt-5.5"
    GPT_5_4 = "gpt-5.4"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_4_NANO = "gpt-5.4-nano"
    GPT_5_3_CODEX = "gpt-5.3-codex"
    GPT_5_3_CODEX_SPARK = "gpt-5.3-codex-spark"
    GPT_5_2 = "gpt-5.2"
    GPT_5_2_CODEX = "gpt-5.2-codex"
    GPT_5_1 = "gpt-5.1"
    GPT_5_1_CODEX_MAX = "gpt-5.1-codex-max"
    GPT_5_1_CODEX_MINI = "gpt-5.1-codex-mini"
    GPT_5_MINI = "gpt-5-mini"
    
    CLAUDE_4_7_OPUS = "claude-opus-4-7"
    CLAUDE_4_6_SONNET = "claude-sonnet-4-6"
    CLAUDE_4_6_OPUS = "claude-opus-4-6"
    CLAUDE_4_5_SONNET = "claude-sonnet-4-5"
    CLAUDE_4_5_OPUS = "claude-opus-4-5"
    CLAUDE_4_5_HAIKU = "claude-haiku-4-5"
    CLAUDE_4_SONNET = "claude-sonnet-4"
    
    GEMINI_3_1_PRO = "gemini-3.1-pro"
    GEMINI_3_FLASH = "gemini-3-flash"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    
    GROK_4_20 = "grok-4-20"
    KIMI_K2_5 = "kimi-k2.5"

@dataclass
class ModelParameterValue:
    """
    A specific value for a model parameter.

    Parameters
    ----------
    id : str
        The parameter identifier.
    value : str
        The value assigned to the parameter.
    """
    id: str
    value: str


@dataclass
class ModelParameters:
    """
    Ergonomic builder for model parameters.

    Provides named fields for well-known parameters so you don't need
    to construct ``ModelParameterValue`` lists by hand.  Any parameter
    set to a non-None value is included in the serialized list.

    Parameters
    ----------
    thinking : str, optional
        Thinking budget level (``"high"``, ``"medium"``, ``"low"``).

    Examples
    --------
    >>> params = ModelParameters(thinking="high")
    >>> model = ModelSelection(CommonModels.CLAUDE_4_6_SONNET, params=params)

    >>> # Or build incrementally:
    >>> params = ModelParameters()
    >>> params.thinking = "high"
    >>> model = ModelSelection("claude-sonnet-4-6", params=params)
    """
    thinking: Optional[str] = None

    def to_list(self) -> List[ModelParameterValue]:
        """Convert set fields into a ``List[ModelParameterValue]``."""
        out: List[ModelParameterValue] = []
        if self.thinking is not None:
            out.append(ModelParameterValue(id="thinking", value=self.thinking))
        return out

    def __bool__(self) -> bool:
        return any(v is not None for v in (self.thinking,))


@dataclass
class ModelSelection:
    """
    Specifies a model and its optional parameters for a run.

    Accepts parameters as a raw list, a :class:`ModelParameters` helper,
    or inline via the ``thinking`` shorthand.

    Parameters
    ----------
    id : str
        The unique identifier of the model.
    params : ModelParameters, List[ModelParameterValue], or None
        Model parameters.  A :class:`ModelParameters` instance is
        automatically converted to the wire format.
    thinking : str, optional
        Shorthand — equivalent to
        ``params=ModelParameters(thinking=thinking)``.  Ignored if
        *params* is already provided.

    Examples
    --------
    >>> # Shorthand (cleanest for single params):
    >>> ModelSelection("claude-sonnet-4-6", thinking="high")

    >>> # Via ModelParameters:
    >>> ModelSelection("claude-sonnet-4-6", params=ModelParameters(thinking="high"))

    >>> # Raw (full control):
    >>> ModelSelection("claude-sonnet-4-6", params=[ModelParameterValue("thinking", "high")])
    """
    id: str
    params: Optional[Union[List[ModelParameterValue], "ModelParameters"]] = None
    thinking: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.params is None and self.thinking is not None:
            self.params = ModelParameters(thinking=self.thinking)

    @property
    def resolved_params(self) -> Optional[List[ModelParameterValue]]:
        """Return params as a flat list, converting ModelParameters if needed."""
        if self.params is None:
            return None
        if isinstance(self.params, ModelParameters):
            result = self.params.to_list()
            return result if result else None
        return self.params

@dataclass
class ModelParameterDefinition:
    """
    Defines a parameter that can be configured for a model.

    Parameters
    ----------
    id : str
        The parameter identifier.
    values : List[dict]
        A list of allowed values, each a dict with 'value' and optional 'displayName'.
    displayName : Optional[str], optional
        A human-readable name for the parameter, by default None.
    """
    id: str
    values: List[dict] # Array<{ value: string; displayName?: string }>
    displayName: Optional[str] = None

@dataclass
class ModelVariant:
    """
    A specific configuration variant of a model.

    Parameters
    ----------
    params : List[ModelParameterValue]
        The parameter values that define this variant.
    displayName : str
        A human-readable name for the variant.
    description : Optional[str], optional
        A description of the variant, by default None.
    isDefault : Optional[bool], optional
        Whether this is the default variant for the model, by default None.
    """
    params: List[ModelParameterValue]
    displayName: str
    description: Optional[str] = None
    isDefault: Optional[bool] = None

@dataclass
class ModelListItem:
    """
    An item in a list of available models.

    Parameters
    ----------
    id : str
        The unique identifier of the model.
    displayName : str
        A human-readable name for the model.
    description : Optional[str], optional
        A description of the model, by default None.
    parameters : Optional[List[ModelParameterDefinition]], optional
        Definitions of configurable parameters, by default None.
    variants : Optional[List[ModelVariant]], optional
        Available variants of the model, by default None.
    """
    id: str
    displayName: str
    description: Optional[str] = None
    parameters: Optional[List[ModelParameterDefinition]] = None
    variants: Optional[List[ModelVariant]] = None
