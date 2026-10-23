"""Generate Random name combinations."""

import bisect
from dataclasses import dataclass
import random
from os.path import abspath, join, dirname

__author__ = "josh"

FREQUENCY_TOLERANCE = (
    0.001  # Accounts for floating point precision in cumulative frequencies
)


@dataclass(frozen=True)
class NameFrequency:
    name: str
    start: float
    end: float


class SimpleNameGenerator:
    """
    A class for generating first and last names

    This class depends on 3 external files that are expected to have 1 name
    per line.  It uses a file for male first names, female first names, and
    then another file for last names.  If your names are not dependent on
    the gender, you could use the same file for male and female first names.

    """

    def __init__(self, rng: random.Random | None = None):
        """
        Create the object using the 3 external files.

        This function will call 2 methods, 1 to read in the data from the
        three text files, and another to make the name lists.

        """
        self.rng = rng or random.Random()
        self.female_name_file = self.full_path("names.female.first.txt")
        self.male_name_file = self.full_path("names.male.first.txt")
        self.last_name_file = self.full_path("names.last.txt")
        self.male_names = []
        self.female_names = []
        self.last_names = []
        self.male_name_data = ""
        self.female_name_data = ""
        self.last_name_data = ""
        self.read_data()
        self.make_name_lists()

    @staticmethod
    def full_path(filename):
        """Returns the full path to a filename."""
        return abspath(join(dirname(__file__), filename))

    def _normalize_gender(self, gender: str) -> str:
        g = gender.lower()
        if g in {"m", "male"}:
            return "male"
        if g in {"f", "female"}:
            return "female"
        return "either"

    def read_data(self):
        """Read in the data from each of the 3 files."""
        self.male_name_data = self._read_name_file(self.male_name_file)
        self.female_name_data = self._read_name_file(self.female_name_file)
        self.last_name_data = self._read_name_file(self.last_name_file)

    def make_name_lists(self):
        """
        Create lists of names based on the data members.

        The default assumption is that the lines may contain multiple strings,
        but that the name is the first string.

        """
        for line in self.male_name_data:
            self.male_names.append(line.split()[0])
        for line in self.female_name_data:
            self.female_names.append(line.split()[0])
        for line in self.last_name_data:
            self.last_names.append(line.split()[0])
        if not self.male_names or not self.female_names or not self.last_names:
            raise ValueError("One or more name files resulted in empty name lists")

    def first(self, gender: str = "either") -> str:
        """Return a first name."""
        gender = self._normalize_gender(gender)
        if gender == "male":
            return self.rng.choice(self.male_names)
        elif gender == "female":
            return self.rng.choice(self.female_names)
        else:
            all_names = self.male_names + self.female_names
            return self.rng.choice(all_names)

    def last(self) -> str:
        """Return a last name."""
        return self.rng.choice(self.last_names)

    def full(self, gender: str = "either") -> tuple[str, str]:
        """
        Generate a full name, based on the gender.

        We just pick a random choice from the correct gender names list and
        tuple it together with a random choice from the last names list.

        """
        gender = self._normalize_gender(gender)

        if gender == "male":
            return self.first(gender), self.last()
        elif gender == "female":
            return self.first("f"), self.last()
        else:
            return self.first("either"), self.last()

    def _read_name_file(self, filepath: str) -> list[str]:
        """Read a name file and return its lines."""
        try:
            with open(filepath) as f:
                return f.readlines()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Required name file not found: {filepath}") from e


class NameGenerator(SimpleNameGenerator):
    """
    Extends the SimpleNameGenerator class to output random names
    based on actual frequency.

    """

    def _max_range(self, names: list[NameFrequency]) -> float:
        return names[-1].end

    def make_name_lists(self):
        """Create a name_frequency tuple for each name in each list."""
        self.male_names = []
        self.female_names = []
        self.last_names = []
        self.make_names(self.male_name_data, self.male_names)
        self.make_names(self.female_name_data, self.female_names)
        self.make_names(self.last_name_data, self.last_names)
        if not self.male_names or not self.female_names or not self.last_names:
            raise ValueError("One or more name files resulted in empty name lists")

    @staticmethod
    def make_names(data_list: list[str], name_list: list[NameFrequency]) -> None:
        """
        Actually create the name_frequency tuples here.

        The name needs to be in the first column, and the cumulative
        frequency value needs to be in the third.

        """
        start_range = 0.0
        for line in data_list:
            parts = line.split()
            end_range = float(parts[2])
            name_list.append(
                NameFrequency(
                    name=parts[0],
                    start=start_range,
                    end=end_range,
                )
            )
            start_range = end_range

    def first(self, gender: str = "either") -> str:
        """Return a first name."""
        gender = self._normalize_gender(gender)

        if gender == "male":
            name_list = self.male_names
        elif gender == "female":
            name_list = self.female_names
        else:
            # For "either", randomly pick a gender first
            name_list = self.rng.choice([self.male_names, self.female_names])

        value = self.rng.uniform(0.0, self._max_range(name_list))
        # Binary search for the name
        idx = bisect.bisect_right([n.end for n in name_list], value)
        return name_list[min(idx, len(name_list) - 1)].name

    def last(self) -> str:
        """Return a last name."""
        matching_last_names = []
        last = self.rng.uniform(0.0, self._max_range(self.last_names))
        for name in self.last_names:
            if name.start <= last and name.end + FREQUENCY_TOLERANCE >= last:
                matching_last_names.append(name)
        return self.rng.choice(matching_last_names).name

    def full(self, gender: str = "either") -> tuple[str, str]:
        """
        Generate a random name, based on frequency.

        We pick the correctly gendered name, and a last name from our lists.
        We need to subtract FREQUENCY_TOLERANCE
        from the rlast random number as the random float
        will always (?) have extra digits beyond the thousands place
        which we want to ignore.  Many of the names towards the end of
        last names list have less than 0.001 percent frequency, so their
        start range and end range are equal.  If the random number hits
        one of those, we put all the matching names into a list and
        pick a random choice from that list.

        """
        gender = self._normalize_gender(gender)

        if gender == "male":
            return self.first("m"), self.last()
        elif gender == "female":
            return self.first("f"), self.last()
        else:
            return self.first(), self.last()
