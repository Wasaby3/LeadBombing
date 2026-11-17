from __future__ import annotations

import pathlib
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .chrome import ChromeOptions
from .logger import LogOptions
from .parser import ParserOptions
from .version import config_version
from .writer import FilterOptions, WriterOptions


class Configuration(BaseModel):
    """Configuration model."""
    model_config = ConfigDict(validate_assignment=True)

    log: LogOptions = Field(default_factory=LogOptions)
    writer: WriterOptions = Field(default_factory=WriterOptions)
    chrome: ChromeOptions = Field(default_factory=ChromeOptions)
    parser: ParserOptions = Field(default_factory=ParserOptions)
    filters: FilterOptions = Field(default_factory=FilterOptions)
    path: Optional[pathlib.Path] = None
    version: str = config_version
