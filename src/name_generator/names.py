"""Generate Random name combinations."""
from collections import namedtuple
import random
from os.path import abspath, join, dirname
__author__ = 'josh'

MALE_GENDER = ["m", "male", "M", "Male", "MALE"]
FEMALE_GENDER = ["f", "female", "F", "Female", "FEMALE"]
MALE_TOTAL_PROB = 90.04
FEMALE_TOTAL_PROB = 90.024
LAST_TOTAL_PROB = 90.483


class SimpleNameGenerator(object):
    """
    A class for generating first and last names

    This class depends on 3 external files that are expected to have 1 name
    per line.  It uses a file for male first names, female first names, and
    then another file for last names.  If your names are not dependent on
    the gender, you could use the same file for male and female first names.

    """
    def __init__(self):
        """
        Create the object using the 3 external files.

        This function will call 2 methods, 1 to read in the data from the
        three text files, and another to make the name lists.

        """
        self.female_name_file = self.full_path('names.female.first.txt')
        self.male_name_file = self.full_path('names.male.first.txt')
        self.last_name_file = self.full_path('names.last.txt')
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

    def read_data(self):
        """Read in the data from each of the 3 files."""
        with open(self.male_name_file) as mnf:
            self.male_name_data = mnf.readlines()
        with open(self.female_name_file) as fnf:
            self.female_name_data = fnf.readlines()
        with open(self.last_name_file) as lnf:
            self.last_name_data = lnf.readlines()

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

    def first(self, gender="either"):
        """Return a first name."""
        if gender in MALE_GENDER:
            return random.choice(self.male_names)
        elif gender in FEMALE_GENDER:
            return random.choice(self.female_names)
        else:
            either = [self.male_names, self.female_names]
            return random.choice(random.choices(either, weights=map(len, either))[0])

    def last(self):
        """Return a last name."""
        return random.choice(self.last_names)

    def full(self, gender="either"):
        """
        Generate a full name, based on the gender.

        We just pick a random choice from the correct gender names list and
        tuple it together with a random choice from the last names list.

        """
        if gender in MALE_GENDER:
            return self.first(gender), self.last()
        elif gender in FEMALE_GENDER:
            return self.first("f"), self.last()
        else:
            return self.first("either"), self.last()


class NameGenerator(SimpleNameGenerator):
    """
    Extends the SimpleNameGenerator class to output random names
    based on actual frequency.

    """
    def make_name_lists(self):
        """Create a name_frequency tuple for each name in each list."""
        self.male_names = []
        self.female_names = []
        self.last_names = []
        self.make_names(self.male_name_data, self.male_names)
        self.make_names(self.female_name_data, self.female_names)
        self.make_names(self.last_name_data, self.last_names)

    @staticmethod
    def make_names(data_list, name_list):
        """
        Actually create the name_frequency tuples here.

        The name needs to be in the first column, and the cumulative
        frequency value needs to be in the third.

        """
        name_frequency = namedtuple('name_frequency', 'name start end')
        start_range = 0.0
        for line in data_list:
            end_range = float(line.split()[2])
            name_list.append(name_frequency(
                    line.split()[0],
                    start_range, end_range
                    )
                )
            start_range = end_range

    def first(self, gender="either"):
        """Return a first name."""
        matching_names = []
        if gender in MALE_GENDER:
            first = random.uniform(0.0, MALE_TOTAL_PROB)
            for name in self.male_names:
                if name.start <= first and name.end >= first - 0.001:
                    matching_names.append(name)
        elif gender in FEMALE_GENDER:
            first = random.uniform(0.0, FEMALE_TOTAL_PROB)
            for name in self.female_names:
                if name.start <= first and name.end >= first - 0.001:
                    matching_names.append(name)
        else:
            first = random.uniform(0.0, MALE_TOTAL_PROB)
            for name in self.male_names:
                if name.start <= first and name.end >= first - 0.001:
                    matching_names.append(name)
            first = random.uniform(0.0, FEMALE_TOTAL_PROB)
            for name in self.female_names:
                if name.start <= first and name.end >= first - 0.001:
                    matching_names.append(name)
        return random.choice(matching_names).name

    def last(self):
        """Return a last name."""
        matching_last_names = []
        last = random.uniform(0.0, LAST_TOTAL_PROB)
        for name in self.last_names:
            if name.start <= last and name.end >= last - 0.001:
                matching_last_names.append(name)
        return random.choice(matching_last_names).name

    def full(self, gender="male"):
        """
        Generate a random name, based on frequency.

        We pick the correctly gendered name, and a last name from our lists.
        The magic numbers, e.g. 90.483, 90.040, and 90.024 are picked
        from the name list files by manual inspection.  We need to
        subtract -0.001 from the rlast random number as the random float
        will always (?) have extra digits beyond the thousands place
        which we want to ignore.  Many of the names towards the end of
        last names list have less than 0.001 percent frequency, so their
        start range and end range are equal.  If the random number hits
        one of those, we put all the matching names into a list and
        pick a random choice from that list.

        """
        if gender in MALE_GENDER:
            return self.first("m"), self.last()
        elif gender in FEMALE_GENDER:
            return self.first("f"), self.last()
        else:
            return self.first(), self.last()
