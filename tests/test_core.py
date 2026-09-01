import unittest

import numpy as np

from assistant_server import (
    MIN_SPEECH_MS,
    SAMPLE_RATE,
    SpeechSegmenter,
    command_looks_like_stop,
    extract_complete_sentences,
    int32_stream_to_int16,
    is_noise_transcript_text,
    pcm_stream_to_int16,
    recv_auth_line,
)


class TestDecode(unittest.TestCase):
    def test_int32_decode_scales_and_clips(self):
        src = np.array([0, 1000, -1000, 400000, -400000], dtype=np.int32).tobytes()
        out = int32_stream_to_int16(src)
        self.assertEqual(out.dtype, np.int16)
        self.assertEqual(len(out), 5)
        self.assertTrue(np.max(out) <= 32767)
        self.assertTrue(np.min(out) >= -32768)

    def test_pcm_stream_to_int16_handles_16bit_and_32bit(self):
        src16 = np.array([100, -200, 300, -400, 500], dtype=np.int16).tobytes()
        out16 = pcm_stream_to_int16(src16)
        self.assertEqual(out16.dtype, np.int16)
        self.assertEqual(len(out16), 5)
        np.testing.assert_array_equal(out16, np.array([100, -200, 300, -400, 500], dtype=np.int16))

        src32 = np.array([0, 1000, -1000], dtype=np.int32).tobytes()
        out32 = pcm_stream_to_int16(src32)
        self.assertEqual(out32.dtype, np.int16)
        self.assertEqual(len(out32), 3)


class TestSentenceChunker(unittest.TestCase):
    def test_extract_complete_sentences(self):
        sentences, rem = extract_complete_sentences("Hello master! How can I help you today? I am ready")
        self.assertEqual(sentences, ["Hello master!", "How can I help you today?"])
        self.assertEqual(rem, " I am ready")


class TestNoiseFilter(unittest.TestCase):
    def test_noise_words_are_filtered(self):
        self.assertTrue(is_noise_transcript_text("you"))
        self.assertTrue(is_noise_transcript_text("uh"))
        self.assertTrue(is_noise_transcript_text(""))

    def test_normal_sentence_not_filtered(self):
        self.assertFalse(is_noise_transcript_text("what time is it"))

    def test_stop_commands_are_detected(self):
        self.assertTrue(command_looks_like_stop("stop"))
        self.assertTrue(command_looks_like_stop("Stop talking."))
        self.assertTrue(command_looks_like_stop("cancel"))
        self.assertFalse(command_looks_like_stop("stop the fan"))


class FakeSocket:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.timeout = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, _size):
        return self.payload


class TestAuthHandshake(unittest.TestCase):
    def test_auth_line_preserves_buffered_audio(self):
        line, rest = recv_auth_line(FakeSocket(b"AUTH secret\nabcd"))
        self.assertEqual(line, "AUTH secret")
        self.assertEqual(rest, b"abcd")


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
