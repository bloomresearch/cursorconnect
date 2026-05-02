from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

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
class ModelSelection:
    """
    Specifies a model and its optional parameters for a run.

    Parameters
    ----------
    id : str
        The unique identifier of the model.
    params : Optional[List[ModelParameterValue]], optional
        A list of parameter values for the model, by default None.
    """
    id: str
    params: Optional[List[ModelParameterValue]] = None

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
