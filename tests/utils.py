class FakeRNG:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


class NullLogger:
    def info(self, msg, *args, **kwargs):
        pass

    def debug(self, msg, *args, **kwargs):
        pass

    def trace(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        pass

    def critical(self, msg, *args, **kwargs):
        pass
