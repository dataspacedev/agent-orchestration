def echo(text: str) -> str:
    return text


def reverse_text(text: str) -> str:
    return text[::-1]


def word_count(text: str) -> dict[str, int]:
    return {"words": len(text.split()), "characters": len(text)}
