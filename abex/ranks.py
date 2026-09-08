"""Rank ladder, appointment titles and merit sources.

This is the single source of truth for the promotion system. Everything else
in the bot reads from here, so changing a threshold or adding a merit source
only ever means editing this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    JUNIOR_BUREAUCRAT = "Junior Bureaucrat"
    SENIOR_BUREAUCRAT = "Senior Bureaucrat"


@dataclass(frozen=True)
class Rank:
    key: str
    name: str
    merit: int
    tier: Tier


# Ordered low to high. Index in this list is the rank's position on the ladder.
RANKS: tuple[Rank, ...] = (
    Rank("loyalist", "Loyalist", 0, Tier.JUNIOR_BUREAUCRAT),
    Rank("junior_loyalist", "Junior Loyalist", 2, Tier.JUNIOR_BUREAUCRAT),
    Rank("senior_loyalist", "Senior Loyalist", 10, Tier.JUNIOR_BUREAUCRAT),
    Rank("group_loyalist", "Group Loyalist", 15, Tier.JUNIOR_BUREAUCRAT),
    Rank("section_loyalist", "Section Loyalist", 25, Tier.JUNIOR_BUREAUCRAT),
    Rank("unit_loyalist", "Unit Loyalist", 35, Tier.JUNIOR_BUREAUCRAT),
    Rank("group_official", "Group Official", 75, Tier.SENIOR_BUREAUCRAT),
    Rank("service_official", "Service Official", 135, Tier.SENIOR_BUREAUCRAT),
    Rank("section_official", "Section Official", 210, Tier.SENIOR_BUREAUCRAT),
    Rank("district_official", "District Official", 300, Tier.SENIOR_BUREAUCRAT),
    Rank("precinct_official", "Precinct Official", 400, Tier.SENIOR_BUREAUCRAT),
)

RANK_BY_KEY: dict[str, Rank] = {r.key: r for r in RANKS}
RANK_INDEX: dict[str, int] = {r.key: i for i, r in enumerate(RANKS)}

LOWEST_RANK = RANKS[0]
HIGHEST_RANK = RANKS[-1]

# Advancing past this rank requires the oath and uniform flags. Straight out of
# the promotion guide: "Group Loyalist (Uniform and Oath Required to Advance
# Further)".
GATE_RANK_KEY = "group_loyalist"


def rank_for_merit(merit: int) -> Rank:
    """Highest rank whose threshold the merit total meets, ignoring the gate."""
    earned = LOWEST_RANK
    for rank in RANKS:
        if merit >= rank.merit:
            earned = rank
        else:
            break
    return earned


def entitled_rank(merit: int, oath: bool, uniform: bool) -> Rank:
    """Rank a member is actually entitled to, with the oath/uniform gate applied."""
    earned = rank_for_merit(merit)
    if oath and uniform:
        return earned
    gate = RANK_BY_KEY[GATE_RANK_KEY]
    if RANK_INDEX[earned.key] > RANK_INDEX[gate.key]:
        return gate
    return earned


def is_gated(merit: int, oath: bool, uniform: bool) -> bool:
    """True when merit alone would promote them but the gate is holding them."""
    return RANK_INDEX[rank_for_merit(merit).key] > RANK_INDEX[entitled_rank(merit, oath, uniform).key]


def next_rank(current: Rank) -> Rank | None:
    index = RANK_INDEX[current.key] + 1
    return RANKS[index] if index < len(RANKS) else None


class Cap(str, Enum):
    NONE = "none"
    ONCE = "once"        # lifetime, one grant per member
    DAILY = "daily"      # one grant per UTC calendar day
    WEEKLY_MERIT = "weekly_merit"  # capped by total merit over a rolling 7 days


@dataclass(frozen=True)
class MeritSource:
    key: str
    label: str
    merit: int
    cap: Cap
    cap_value: int = 0
    note: str = ""
    officers_only_subject: bool = False  # subject must be Senior Bureaucrat or higher


MERIT_SOURCES: tuple[MeritSource, ...] = (
    MeritSource("oath", "In-game branch oath", 2, Cap.ONCE, note="One time"),
    MeritSource("uniform", "Skin on division uniform", 10, Cap.ONCE, note="One time"),
    MeritSource("rp_character", "Roleplay character submitted", 5, Cap.ONCE, note="One time"),
    MeritSource("event", "Standard event attendance", 5, Cap.DAILY, note="3 or more attendees, once per day"),
    MeritSource("operation", "Official operation", 8, Cap.NONE),
    MeritSource("raid", "Official raid or server battle", 10, Cap.NONE),
    MeritSource(
        "host_event",
        "Hosted an event",
        5,
        Cap.NONE,
        note="3+ attendees, Senior Bureaucrat and above",
        officers_only_subject=True,
    ),
    MeritSource("recruit", "Recruited an active member", 5, Cap.NONE, note="Member who joins a branch or division"),
    MeritSource("quota", "Work quota completed", 5, Cap.NONE),
    MeritSource("tithe", "Imperium tithe", 1, Cap.WEEKLY_MERIT, cap_value=20, note="1 merit per 1000 tithed, 20 per week"),
)

SOURCE_BY_KEY: dict[str, MeritSource] = {s.key: s for s in MERIT_SOURCES}

# Sources granted through /merit log. Tithe has its own command because the
# officer enters an amount tithed rather than a fixed activity.
LOGGABLE_SOURCES: tuple[MeritSource, ...] = tuple(s for s in MERIT_SOURCES if s.key != "tithe")

TITHE_SOURCE = SOURCE_BY_KEY["tithe"]
TITHE_PER_MERIT = 1000

# Manual sources that never come from the activity table.
SOURCE_MANUAL = "manual"
SOURCE_CORRECTION = "correction"

# The rank a member must hold to be credited for hosting an event.
HOST_MIN_RANK_KEY = "group_official"


def merit_from_tithe(amount: int) -> int:
    """1 merit per 1000 tithed, rounded down."""
    return amount // TITHE_PER_MERIT


@dataclass(frozen=True)
class Appointment:
    key: str
    name: str
    group: str
    description: str


# Appointments are conferred, never earned. The bot records them and shows them
# on the profile card, it does not hand them out on merit.
APPOINTMENTS: tuple[Appointment, ...] = (
    Appointment("counselor", "Counselor to the Imperium", "Supreme Command", "Supreme Executive and Regent"),
    Appointment("grand_chancellor", "Grand Chancellor", "Supreme Command", "Head of Government"),
    Appointment("grand_siridar", "Grand Siridar", "Supreme Command", "President of the Council of Governors"),
    Appointment("grand_marshal", "Grand Marshal", "Supreme Command", "Supreme Commander of the Armed Forces"),
    Appointment("chairman_compao", "Chairman of COMPAO", "Supreme Command", "Supreme Head of the Commission"),
    Appointment("abexilian_marshal", "Abexilian Marshal", "Supreme Command", "Head of the Enlightenment Group"),
    Appointment("deputy_chairman_compao", "Deputy Chairman of COMPAO", "Branch Command", "Deputy Lead"),
    Appointment("group_leader", "Group Leader", "High Command", "Highest rank"),
    Appointment("national_leader", "National Leader", "High Command", "National or Continental Directorate"),
    Appointment("state_leader", "State Leader", "High Command", "Sector or State Governor"),
    Appointment("department_leader", "Department Leader", "Regional Command", "Lead Operational Directorate or Senior PLO"),
    Appointment("regional_leader", "Regional Leader", "Regional Command", "Regional Governance or Strike Unit Lead"),
    Appointment("provincial_leader", "Provincial Leader", "Regional Command", "Provincial Administrator or Auxiliary Lead"),
    Appointment("municipal_leader", "Municipal Leader", "Regional Command", "Urban District Overseer or Senior Officer"),
    Appointment("siridar", "Siridar", "Council of Governors", "Continental, Empire or large organisation leader"),
    Appointment("governor", "Governor", "Council of Governors", "National, provincial or medium organisation leader"),
    Appointment("prefect", "Prefect", "Council of Governors", "Single town, claim or small organisation"),
)

APPOINTMENT_BY_KEY: dict[str, Appointment] = {a.key: a for a in APPOINTMENTS}

# Appointments from Municipal Leader upwards are commissioned officer titles.
COMMISSIONED_GROUPS = ("Regional Command", "High Command", "Branch Command", "Supreme Command")


@dataclass(frozen=True)
class Track:
    """One of the parallel rank ladders.

    Every branch promotes on the same merit thresholds, but the titles differ.
    COMPAO uses the standard titles with its own set of roles. The Civil
    Service renames every step, so a Section Official there is a Supervisor.
    """

    key: str
    label: str
    names: dict[str, str]
    short: str = ""

    def title(self, key: str) -> str:
        """Display name for a rank or appointment on this track."""
        if key in self.names:
            return self.names[key]
        rank = RANK_BY_KEY.get(key)
        if rank is not None:
            return rank.name
        appointment = APPOINTMENT_BY_KEY.get(key)
        return appointment.name if appointment else key.replace("_", " ").title()


TRACK_BASE = "base"
TRACK_COMPAO = "compao"
TRACK_CIVIL = "civil_service"

# The Civil Service is the only track that renames the ladder. Base and COMPAO
# both use the titles from the promotion guide, they just hold separate roles.
_CIVIL_NAMES = {
    "loyalist": "Intern",
    "junior_loyalist": "Junior Clerk",
    "senior_loyalist": "Senior Clerk",
    "group_loyalist": "Administrative Clerk",
    "section_loyalist": "Supervisory Clerk",
    "unit_loyalist": "Chief Clerk",
    "group_official": "Probationary Supervisor",
    "service_official": "Junior Supervisor",
    "section_official": "Supervisor",
    "district_official": "Senior Supervisor",
    "precinct_official": "Chief Supervisor",
    "municipal_leader": "Assistant Manager",
    "provincial_leader": "Manager",
    "regional_leader": "Senior Manager",
    "department_leader": "Vice President",
    "state_leader": "Senior Vice President",
    "national_leader": "Executive Vice President",
    "group_leader": "President",
}

TRACKS: dict[str, Track] = {
    TRACK_BASE: Track(TRACK_BASE, "Abexilian Remnant", {}, short="Bureaucracy"),
    TRACK_COMPAO: Track(
        TRACK_COMPAO,
        "Commission for the Promotion of the Abexilian Order",
        {},
        short="Commission",
    ),
    TRACK_CIVIL: Track(TRACK_CIVIL, "Civil Service", _CIVIL_NAMES, short="Civil Service"),
}


def get_track(key: str | None) -> Track:
    return TRACKS.get(key or TRACK_BASE, TRACKS[TRACK_BASE])
