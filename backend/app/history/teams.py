"""Team names: football-data.co.uk uses short forms ("Man United", "Nott'm Forest").

Viewers and analysts write them many ways ("Manchester United", "Man U", "Forest",
"Spurs"), so every name is resolved to the canonical form used in the data.
"""

import re

# Canonical name -> extra aliases (the canonical name itself always matches).
# Nicknames that are ambiguous across clubs ("reds", "blues", "united", "city") are left out on purpose.
ALIASES: dict[str, tuple[str, ...]] = {
    "Arsenal": ("arsenal fc", "gunners", "arsenali"),
    "Aston Villa": ("villa",),
    "Barnsley": (),
    "Birmingham": ("birmingham city",),
    "Blackburn": ("blackburn rovers",),
    "Blackpool": (),
    "Bolton": ("bolton wanderers",),
    "Bournemouth": ("afc bournemouth", "cherries"),
    "Bradford": ("bradford city",),
    "Brentford": ("bees",),
    "Brighton": ("brighton & hove albion", "brighton and hove albion", "seagulls"),
    "Burnley": ("clarets",),
    "Cardiff": ("cardiff city",),
    "Charlton": ("charlton athletic",),
    "Chelsea": ("chelsea fc",),
    "Coventry": ("coventry city",),
    "Crystal Palace": ("palace",),
    "Derby": ("derby county",),
    "Everton": ("toffees",),
    "Fulham": (),
    "Huddersfield": ("huddersfield town",),
    "Hull": ("hull city",),
    "Ipswich": ("ipswich town",),
    "Leeds": ("leeds united",),
    "Leicester": ("leicester city", "foxes"),
    "Liverpool": ("liverpool fc",),
    "Luton": ("luton town",),
    "Man City": ("manchester city", "mancity"),
    "Man United": ("manchester united", "man utd", "man u", "manu"),
    "Middlesbrough": ("boro",),
    "Newcastle": ("newcastle united", "magpies"),
    "Norwich": ("norwich city",),
    "Nott'm Forest": ("nottingham forest", "nottm forest", "forest"),
    "Oldham": ("oldham athletic",),
    "Portsmouth": ("pompey",),
    "QPR": ("queens park rangers",),
    "Reading": (),
    "Sheffield United": ("sheffield utd", "sheff utd", "blades"),
    "Sheffield Weds": ("sheffield wednesday", "sheff wed"),
    "Southampton": ("saints",),
    "Stoke": ("stoke city",),
    "Sunderland": (),
    "Swansea": ("swansea city",),
    "Swindon": ("swindon town",),
    "Tottenham": ("tottenham hotspur", "spurs"),
    "Watford": (),
    "West Brom": ("west bromwich albion", "west bromwich", "baggies"),
    "West Ham": ("west ham united", "hammers"),
    "Wigan": ("wigan athletic",),
    "Wimbledon": (),
    "Wolves": ("wolverhampton", "wolverhampton wanderers"),
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower().replace("’", "'"))


_LOOKUP: dict[str, str] = {}
for _canonical, _extra in ALIASES.items():
    for _alias in (_canonical, *_extra):
        _LOOKUP[_norm(_alias)] = _canonical


def canonical_team(name: str, known: set[str] | None = None) -> str | None:
    """Canonical data name for ``name``, or None if unknown.

    ``known`` (names actually present in the data) also matches exactly, so clubs
    not in ALIASES still work by their data name.
    """
    key = _norm(name).lstrip("@")
    if key in _LOOKUP:
        return _LOOKUP[key]
    if known:
        for team in known:
            if _norm(team) == key:
                return team
    return None


def find_teams_in_text(text: str, known: set[str]) -> list[str]:
    """Teams mentioned in free text, in order of appearance (longest aliases win)."""
    aliases = {a: c for a, c in _LOOKUP.items() if c in known}
    aliases.update({_norm(t): t for t in known})
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r")(?!\w)")
    found: list[str] = []
    for match in pattern.finditer(_norm(text)):
        team = aliases[match.group(1)]
        if team not in found:
            found.append(team)
    return found
