import src.game.game_exceptions as game_exceptions
"""The Bases class."""


class Bases(object):
    """Keep track of the base runners."""
    def __init__(self):
        """Initialize the bases to be empty.

        The Bases are [first, second, third]
        0 implies empty.  Base runners will be represented by a
        non-zero integer.

        """
        self.bases = [0, 0, 0]

    def __str__(self):
        """Output as a string."""
        if self.bases == [0, 0, 0]:
            return "Bases empty."
        if self.men_on() == 1:
            if self.bases[0] != 0:
                base = "first"
            elif self.bases[1] != 0:
                base = "second"
            elif self.bases[2] != 0:
                base = "third"
            else:
                return ""
            return "Runner on %s." % base
        elif self.men_on() == 2:
            if self.bases[0] == 0:
                return "Runners on second and third."
            if self.bases[1] == 0:
                return "Runners at first and third."
            return "Runners at first and second."
        elif self.men_on() == 3:
            return "Bases loaded."

    def __iter__(self):
        """Make it iterable."""
        return iter(self.bases)

    def __getitem__(self, index):
        """Make it index-able."""
        if isinstance(index, str):
            if index == "first":
                index = 0
            elif index == "second":
                index = 1
            elif index == "third":
                index = 2
        return self.bases[index]

    def __setitem__(self, index, value):
        """Make it index-able."""
        if isinstance(index, str):
            if index == "first":
                index = 0
            elif index == "second":
                index = 1
            elif index == "third":
                index = 2
        self.bases[index] = value

    def advance(self, fro, dest=None):
        """
        Advance a runner from fro to dest. If no dest specified just
        advance one base.
        :param fro: the base to advance from
        :param dest: the base to advance to

        """
        if dest == 0:
            raise game_exceptions.InvalidAdvance()
        if not dest:
            dest = fro + 1
        if fro >= dest:
            raise game_exceptions.InvalidAdvance()
        if fro == 2 or dest >= 3:
            scored = self.bases[fro]
            self.clear(fro)
            return scored
        if self.bases[dest] != 0:
            raise game_exceptions.AdvanceToOccupiedBase()
        if self.bases[fro] == 0:
            raise game_exceptions.NoRunnerToAdvance()
        for counter in range(fro + 1, dest):
            if self.bases[counter] != 0:
                raise game_exceptions.AdvancePastOccupiedBase()
        self.bases[dest] = self.bases[fro]
        self.bases[fro] = 0

    def advance_many(self, advance_list):
        """
        Advance base runners for each tuple in the advance_list.

        :param advance_list: list of tuples.  Each tuple needs to be sent
        to advance.  It will return a list of scorers, if there are any,
        otherwise it will return an empty list.

        """
        if isinstance(advance_list, tuple):
            advance_list = [advance_list]
        scorers = []
        for adv in advance_list:
            if adv[0] == 2:
                scorer = self.advance(adv[0], adv[1])
                if scorer:
                    scorers.append(scorer)
        for adv in advance_list:
            if adv[0] == 1:
                scorer = self.advance(adv[0], adv[1])
                if scorer:
                    scorers.append(scorer)
        for adv in advance_list:
            if adv[0] == 0:
                scorer = self.advance(adv[0], adv[1])
                if scorer:
                    scorers.append(scorer)
        return scorers

    def advance_all(self):
        """Advance all runners 1 base.  Clear first base."""
        scored = self.bases[2]
        self.bases[2] = self.bases[1]
        self.bases[1] = self.bases[0]
        self.bases[0] = 0
        return scored

    def clear(self, to_clear=(0, 1, 2)):
        """
        Clear bases. to_clear is a list of bases to clear.
        Alternatively, it could be a single integer.
        :param to_clear: a list of bases to clear, or a single base

        """
        if isinstance(to_clear, int):
            to_clear = [to_clear]
        for base in to_clear:
            self.bases[base] = 0

    def men_on(self):
        """Return the number of runner(s) on base."""
        on_base = 0
        for index in self.bases:
            if index != 0:
                on_base += 1
        return on_base

    def empty_base(self, base):
        """
        Tests if a base is empty.

        Returns True if the base is empty, false otherwise.
        Special case for home.

        :param base: the base to test

        """
        if self.bases[base] == 0:
            return True
        return False
