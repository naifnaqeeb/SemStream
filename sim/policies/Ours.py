import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sabre
from agent.state_machine import ContentAwareStateMachine


class Ours(sabre.Abr):
    def __init__(self, config):
        self.state_machine = ContentAwareStateMachine()

    def get_quality_delay(self, segment_index):
        bitrates_kbps = self.session.manifest.bitrates
        bandwidth_kbps = self.session.get_throughput()
        content_labels = self.session.manifest.content_labels
        content_label = content_labels[segment_index] if content_labels else None
        quality = self.state_machine.next_quality(bitrates_kbps, bandwidth_kbps, content_label)
        return (quality, 0)
