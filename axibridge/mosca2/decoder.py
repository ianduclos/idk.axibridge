"""Authored two-action decoder. The rates are biological outputs; the names aren't."""
class Decoder:
    def __init__(self):
        self.mode='continue'; self.changed_ms=0; self.candidate=None; self.candidate_since=0
    def step(self,t_ms,hz):
        want='leave' if hz>=45 else 'continue'
        if want!=self.candidate:
            self.candidate=want;self.candidate_since=t_ms
        if want!=self.mode and t_ms-self.candidate_since>=300 and t_ms-self.changed_ms>=1000:
            before=self.mode;self.mode=want;self.changed_ms=t_ms
            return dict(t_ms=t_ms,before=before,after=want,feature_hz=hz,
                        threshold_hz=45,persistence_ms=t_ms-self.candidate_since,kind='mode')
