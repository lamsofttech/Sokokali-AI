from config import APP_NAME


class SokokaliAI:
    """Local rule-based prototype; replace with an LLM integration later."""

    def respond(self, message: str) -> str:
        text = message.strip().lower()
        if not text:
            return "Please ask me a sports question."
        if any(word in text for word in ("hello", "habari", "hi")):
            return f"Karibu! Mimi ni {APP_NAME}. Tuongee sports!"
        if "prediction" in text or "predict" in text:
            return "I can demonstrate a prediction, but live sports data is not connected yet."
        if "score" in text or "result" in text:
            return "Live scores are not connected yet. I won't invent match results."
        return "Asante kwa comment yako! Ask me about sports or predictions."
