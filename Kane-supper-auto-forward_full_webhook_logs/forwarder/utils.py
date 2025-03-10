
def should_forward(message):
    if message.text and "keyword" in message.text.lower():
        return True
    if message.sticker:
        return True
    return False
