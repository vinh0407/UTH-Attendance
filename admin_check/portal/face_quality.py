"""Image quality and vector matching; these checks do not prove liveness."""
import cv2
import numpy as np
from django.conf import settings


def assess_face(image, face):
    bbox = np.asarray(face.bbox, dtype=float)
    if bbox.shape != (4,) or not np.isfinite(bbox).all():
        return {'ok': False, 'code': 'INVALID_FACE', 'message': 'Face could not be located.'}
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox.astype(int)
    crop = image[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
    code, message = 'OK', 'Face quality accepted.'
    score = float(getattr(face, 'det_score', 0) or 0)
    if not np.isfinite(score) or score < settings.FACE_MIN_DETECTION_SCORE:
        code, message = 'LOW_DETECTION', 'Look straight at the camera and uncover your face.'
    elif crop.size == 0 or min(crop.shape[:2]) < settings.FACE_MIN_SIZE:
        code, message = 'FACE_TOO_SMALL', 'Move closer to the camera.'
    elif x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        code, message = 'FACE_CLIPPED', 'Keep your whole face inside the camera frame.'
    else:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        if brightness < 35 or brightness > 225:
            code, message = 'BAD_LIGHTING', 'Use even lighting; avoid darkness and backlight.'
        elif cv2.Laplacian(gray, cv2.CV_64F).var() < settings.FACE_MIN_SHARPNESS:
            code, message = 'BLURRY_FACE', 'Hold still and let the camera focus.'
    return {'ok': code == 'OK', 'code': code, 'message': message}


class EmbeddingIndex:
    """Normalize once, then compare all samples with one matrix multiplication."""
    def __init__(self, database):
        self.groups = {}
        for identity, samples in database.items():
            for sample in samples:
                vector = np.asarray(sample, dtype=np.float32)
                if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all():
                    continue
                norm = np.linalg.norm(vector)
                if norm <= 0:
                    continue
                names, vectors = self.groups.setdefault(vector.size, ([], []))
                names.append(str(identity))
                vectors.append(vector / norm)
        self.groups = {size: (names, np.stack(vectors)) for size, (names, vectors) in self.groups.items()}

    def match(self, embedding, threshold, margin):
        vector = np.asarray(embedding, dtype=np.float32)
        if vector.ndim != 1 or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 0:
            return 'Unknown', 0., 'INVALID_EMBEDDING'
        group = self.groups.get(vector.size)
        if group is None:
            return 'Unknown', 0., 'NO_MATCH'
        names, matrix = group
        scores = np.clip(matrix @ (vector / np.linalg.norm(vector)), -1., 1.)
        best_by_identity = {}
        for name, score in zip(names, scores):
            best_by_identity[name] = max(float(score), best_by_identity.get(name, -1.))
        ranked = sorted(best_by_identity.items(), key=lambda item: item[1], reverse=True)
        name, best = ranked[0]
        if best <= threshold:
            return 'Unknown', max(0., best), 'NO_MATCH'
        if len(ranked) > 1 and best - ranked[1][1] < margin:
            return 'Unknown', best, 'AMBIGUOUS_MATCH'
        return name, best, 'OK'
