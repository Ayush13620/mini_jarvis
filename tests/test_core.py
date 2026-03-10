import unittest

import numpy as np

from assistant_server import (
    MIN_SPEECH_MS,
    SAMPLE_RATE,
    SpeechSegmenter,
    is_noise_transcript_text,
    int32_stream_to_int16,
)


class TestDecode(unittest.TestCase):
    def test_int32_decode_scales_and_clips(self):
        src = np.array([0, 1000, -1000, 400000, -400000], dtype=np.int32).tobytes()
        out = int32_stream_to_int16(src)
        self.assertEqual(out.dtype, np.int16)
        self.assertEqual(len(out), 5)
        self.assertTrue(np.max(out) <= 32767)
        self.assertTrue(np.min(out) >= -32768)


class TestNoiseFilter(unittest.TestCase):
    def test_noise_words_are_filtered(self):
        self.assertTrue(is_noise_transcript_text("you"))
        self.assertTrue(is_noise_transcript_text("uh"))
        self.assertTrue(is_noise_transcript_text(""))

    def test_normal_sentence_not_filtered(self):
        self.assertFalse(is_noise_transcript_text("what time is it"))


class TestSegmenter(unittest.TestCase):
    def test_segmenter_emits_after_voiced_then_silence(self):
        seg = SpeechSegmenter(SAMPLE_RATE)
        voiced = np.full(1600, 1200, dtype=np.int16)
        silence = np.zeros(1600, dtype=np.int16)

        emitted = None
        for _ in range(4):
            emitted = seg.push(voiced)
            self.assertIsNone(emitted)

        # Feed enough silence chunks to trigger end-of-turn.
        for _ in range(15):
            emitted = seg.push(silence)
            if emitted is not None:
                break

        self.assertIsNotNone(emitted)
        min_samples = int(SAMPLE_RATE * MIN_SPEECH_MS / 1000)
        self.assertGreaterEqual(emitted.size, min_samples)


if __name__ == "__main__":
    unittest.main()
