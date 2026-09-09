class GoalNotServableError(Exception):
    """The case base holds nothing this goal can be composed from, so no diet is produced for it.

    Distinct from :class:`NoSimilarCasesError`, which means retrieval returned nothing at all. Here cases WERE
    retrieved and the consensus still yielded no slot, because the cases carry no reproducible structure: on
    dataset-v3 that is `mantenimiento`, with zero diets in the corpus, and `alta_en_fibra`, whose three diets are
    97-100 % inside the non-composable OTHER bucket.

    It is raised rather than returned as an empty document on purpose. An empty diet looks like a diet and puts the
    burden of noticing on the professional; a refusal names the goal and the reason up front.
    """

    def __init__(self, goal: str, cases: int, gap=None):
        super().__init__(f"the case base cannot serve the goal {goal!r}: {cases} case(s) retrieved, none composable")
        self.goal = goal
        self.cases = cases
        self.gap = gap
