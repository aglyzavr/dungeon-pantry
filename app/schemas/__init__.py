def validate_non_empty(v: str, field_name: str = "This field") -> str:
    """Strip whitespace and reject blank strings."""
    if not v or not v.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return v.strip()
