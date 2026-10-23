# tests/helpers/event_recorder.py


class EventRecorder:
    """Helper to capture events as they're enqueued in the game"""

    def __init__(self, game):
        self.game = game
        self.events = []
        self.original_enqueue = None
        self.original_enqueue_left = None

    def __enter__(self):
        """Start recording by intercepting enqueue operations"""
        recorder = self

        # Save originals
        self.original_enqueue = self.game._enqueue
        self.original_enqueue_left = self.game._enqueue_left

        # Patch _enqueue
        def capture_enqueue(events):
            # events should always be a list here based on _enqueue signature

            for event in events:
                recorder.events.append(event)
            return recorder.original_enqueue(events)

        # Patch _enqueue_left (for followups)
        # def capture_enqueue_left(events):
        #     for event in events:
        #         recorder.events.append(event)
        #     return recorder.original_enqueue_left(events)
        def capture_enqueue_left(events):
            # Handle both single event and list
            if isinstance(events, list):
                for event in events:
                    recorder.events.append(event)
            else:
                recorder.events.append(events)
            return recorder.original_enqueue_left(events)

        self.game._enqueue = capture_enqueue
        self.game._enqueue_left = capture_enqueue_left

        return self

    def __exit__(self, *args):
        """Restore original enqueue methods"""
        self.game._enqueue = self.original_enqueue
        self.game._enqueue_left = self.original_enqueue_left

    def get_events(self, event_type):
        """Get all events of a specific type"""
        return [e for e in self.events if isinstance(e, event_type)]

    def assert_event_count(self, event_type, expected):
        """Assert exact count of event type"""
        actual = len(self.get_events(event_type))
        if actual != expected:
            print(f"\n[RECORDER DEBUG] All captured events ({len(self.events)} total):")
            for i, event in enumerate(self.events):
                print(f"  {i}: {type(event).__name__}")

        assert actual == expected, (
            f"Expected {expected} {event_type.__name__} events, got {actual}"
        )
