"""Sports-betting compliance boundary (Module G).

Sokokali gives sports information that betting audiences may use, so the
broadcast carries regular responsible-gambling reminders for the configured
jurisdiction and age limit. There is deliberately no code here for placing
wagers, deposits, betting-site links or gift-linked betting incentives: those
need a separate approved specification, licensing check and compliance review
before anything is built.
"""

from app.schemas.chat import Language

_REMINDERS = {
    Language.ENGLISH: (
        "Quick reminder, wadau: Sokokali's predictions are estimates, not guarantees. Betting is for adults "
        "{min_age} and over only. Set a limit, never chase losses, and if betting stops being fun, take a break."
    ),
    Language.KISWAHILI: (
        "Ukumbusho, wadau: utabiri wa Sokokali ni makadirio, si uhakika. Kubeti ni kwa watu wazima wenye umri wa "
        "miaka {min_age} na zaidi tu. Weka kikomo, usifukuzie hasara, na kama kubeti si burudani tena, pumzika."
    ),
    Language.SHENG: (
        "Wasee, reminder: predictions za Sokokali ni estimates, si guarantee. Kubet ni ya watu wa {min_age}+ "
        "pekee. Weka limit, usichase losses, na kama si fun tena, chukua break."
    ),
}


class ComplianceService:
    def __init__(self, jurisdiction: str = "KE", min_age: int = 18) -> None:
        self.jurisdiction = jurisdiction
        self.min_age = min_age

    def responsible_gambling_message(self, language: Language) -> str:
        return _REMINDERS[language].format(min_age=self.min_age)
