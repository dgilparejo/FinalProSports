"""Which slots may appear in a proposal for a given client (dataset-v2).

Most slots are regulated on their own by how often they appear among the retrieved cases: if the professional rarely writes a
RECENA for people like this client, the composer's `slot_threshold` drops it. That is a fact about HIS habit, and consensus is the
right judge of it.

MITAD DE ENTRENAMIENTO is different: whether it makes sense depends on a fact about the CLIENT, not on the professional's habit.
An intra-workout intake is meaningless for someone who does not train, and consensus cannot know that — the retrieved cases are
chosen by similarity, and a sedentary client can still be closest to cases of people who train.

The threshold is read off the corpus, not chosen: among the 1.033 diets of dataset-v2, NO diet of a client with declared activity
level 1 or 2 carries the slot (0 of 17), while it appears from level 3 upwards (16 %, 25 %, 32 %, 60 % at level 6). An unknown
activity level does not block it (25,6 % of those diets carry it); there the consensus threshold decides, as for any other slot.
"""
from finalprosports.domain.model import ClientProfile, MealSlot

SEDENTARY_MAX_ACTIVITY = 2          # levels 1-2: 0 of 17 diets in the corpus carry an intra-workout intake
PROFILE_DEPENDENT: frozenset[MealSlot] = frozenset({MealSlot.INTRA_WORKOUT})


def trains(profile: ClientProfile) -> bool:
    """True when the client trains, or when we cannot tell (activity level not declared)."""
    return profile.activity_level is None or profile.activity_level > SEDENTARY_MAX_ACTIVITY


def applies(slot: MealSlot, profile: ClientProfile) -> bool:
    if slot in PROFILE_DEPENDENT:
        return trains(profile)
    return True


def drop_inapplicable(meals, profile: ClientProfile):
    """Returns (meals, dropped_slots): the slots that do not apply to this client are removed from the proposal."""
    kept = tuple(m for m in meals if applies(m.slot, profile))
    dropped = tuple(m.slot.value for m in meals if not applies(m.slot, profile))
    return kept, dropped
