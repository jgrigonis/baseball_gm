Tests with the test_ prefix are in pytest style
Tests with the _test suffix are in unittest style

pytest can run either.
unittest cannot

If a function only touches one subsystem, the test 
should only construct that subsystem.
