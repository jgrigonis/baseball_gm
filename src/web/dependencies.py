from typing import Annotated
from fastapi import Request, Depends

# Your reusable dependency function
def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"

# A handy alias for cleaner injection
IsHTMX = Annotated[bool, Depends(is_htmx)]
