import re

def clean_extracted_text(text: str) -> str:
    """
    Cleans PDF extraction artifacts without altering original text content semantics.
    """
    if not text:
        return ""

    # Fix broken line hyphens: word-\n continuation -> wordcontinuation
    text = re.sub(r'(\b\w+)-\n(\w+\b)', r'\1\2', text)

    # Convert horizontal tabs and multiple horizontal spaces to single space
    # (preserving line breaks)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)

    # Remove trailing spaces on each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    # Normalize repeated blank lines (3 or more newlines down to 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
