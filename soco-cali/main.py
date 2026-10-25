
class Sokokali:
    def __init__(self):
        self.name = "Sokokali"
        self.status = "ONLINE"

    def respond(self, message):
        message = message.lower().strip()

        if "hello" in message or "habari" in message:
            return "Karibu! Mimi ni Sokokali!"

        if "prediction" in message:
            return (
                "Welcome to Sokokali Sports! "
                "Our prediction engine is coming soon."
            )

        return "Asante kwa comment yako! Tuongee sports!"


bot = Sokokali()

print("=" * 40)
print("SOKOKALI AI SYSTEM STARTED")
print("Status:", bot.status)
print("=" * 40)
print("Type 'exit' to stop the program.")

while True:
    message = input("Viewer: ").strip()

    if message.lower() == "exit":
        print("Sokokali: Kwaheri! See you next time!")
        break

    if not message:
        continue

    print("Sokokali:", bot.respond(message))
