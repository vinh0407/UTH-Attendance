"""Synthetic vectors/images test decisions without downloading an AI model."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from . import face_recognition as fr


class FacePipelineTests(SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, value in [('DATABASE_FILE', str(self.root / 'faces.pkl')),
                              ('MY_FACES_DIR', str(self.root / 'students'))]:
            patcher = patch.object(fr, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.image = np.random.default_rng(42).integers(40, 210, (200, 200, 3), dtype=np.uint8)
        self.face = SimpleNamespace(bbox=np.array([30, 30, 170, 170]),
                                    embedding=np.array([1., 0., 0.]), det_score=0.99)

    def recognize(self, database, faces=None, image=None):
        fr.save_database(database)
        with patch.object(fr, 'get_face_app', return_value=SimpleNamespace(
                get=lambda _: faces if faces is not None else [self.face])):
            return fr.recognize_face(self.image if image is None else image)

    def test_ambiguous_identities_are_not_accepted(self):
        result = self.recognize({'A': [[1., 0., 0.]], 'B': [[0.999, 0.01, 0.]]})[0]
        self.assertEqual(result['name'], 'Unknown')
        self.assertEqual(result['quality']['code'], 'AMBIGUOUS_MATCH')

    def test_multiple_samples_of_same_student_are_not_competitors(self):
        result = self.recognize({'A': [[1., 0., 0.], [0.99, 0.01, 0.]], 'B': [[0., 1., 0.]]})[0]
        self.assertEqual(result['name'], 'A')

    def test_weak_detection_does_not_match_even_with_perfect_embedding(self):
        self.face.det_score = 0.2
        result = self.recognize({'A': [[1., 0., 0.]]})[0]
        self.assertEqual(result['name'], 'Unknown')
        self.assertEqual(result['quality']['code'], 'LOW_DETECTION')

    def test_blurry_face_is_rejected(self):
        result = self.recognize({'A': [[1., 0., 0.]]}, image=np.full((200, 200, 3), 128, np.uint8))[0]
        self.assertEqual(result['name'], 'Unknown')
        self.assertEqual(result['quality']['code'], 'BLURRY_FACE')

    def test_register_rejects_multiple_people_without_writing_data(self):
        with patch.object(fr, 'get_face_app', return_value=SimpleNamespace(get=lambda _: [self.face, self.face])):
            success, message = fr.register_face('Student', self.image, student_id='A')
        self.assertFalse(success)
        self.assertIn('one face', message)
        self.assertFalse((self.root / 'faces.pkl').exists())
        self.assertFalse((self.root / 'students').exists())

    def test_replaced_database_refreshes_matches(self):
        self.assertEqual(self.recognize({'A': [[1., 0., 0.]]})[0]['name'], 'A')
        self.assertEqual(self.recognize({'B': [[1., 0., 0.]]})[0]['name'], 'B')

    def test_invalid_embeddings_are_ignored(self):
        result = self.recognize({'broken': [[float('nan'), 0., 0.], [0., 0., 0.]],
                                 'A': [[1., 0., 0.]]})[0]
        self.assertEqual(result['name'], 'A')

    def test_small_face_and_dark_face_return_specific_guidance(self):
        self.face.bbox = np.array([50, 50, 70, 70])
        result = self.recognize({'A': [[1., 0., 0.]]})[0]
        self.assertEqual(result['quality']['code'], 'FACE_TOO_SMALL')
        self.face.bbox = np.array([30, 30, 170, 170])
        result = self.recognize({'A': [[1., 0., 0.]]}, image=np.zeros((200, 200, 3), np.uint8))[0]
        self.assertEqual(result['quality']['code'], 'BAD_LIGHTING')
