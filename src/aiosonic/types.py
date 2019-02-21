"""Types."""
from typing import Dict, Union

QueryDict = Dict[str, Union[str, int, None]]

APIReturn = Union[Dict, bytes]
