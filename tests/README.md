Tests with the test_ prefix are in pytest style
Tests with the _test suffix are in unittest style

pytest can run either.
unittest cannot

If a function only touches one subsystem, the test 
should only construct that subsystem.

Very slow tests are marked veryslow (there's only 1 currently)
slow tests are marked slow.

To run both add the '--slow' and/or '--veryslow' parameters to pytest
